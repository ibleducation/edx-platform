"""
Support tool for changing and granting course entitlements
"""
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.utils.decorators import method_decorator
from edx_rest_framework_extensions.authentication import JwtAuthentication
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from six import text_type

from entitlements.api.v1.permissions import IsAdminOrAuthenticatedReadOnly
from entitlements.api.v1.serializers import SupportCourseEntitlementSerializer
from entitlements.models import CourseEntitlement, CourseEntitlementSupportDetail
from openedx.core.djangoapps.cors_csrf.authentication import SessionAuthenticationCrossDomainCsrf
from lms.djangoapps.support.decorators import require_support_permission


class EntitlementSupportView(viewsets.ModelViewSet):
    """
    Allows viewing and changing learner course entitlements, used the support team.
    """
    authentication_classes = (JwtAuthentication, SessionAuthenticationCrossDomainCsrf,)
    permission_classes = (permissions.IsAuthenticated, IsAdminOrAuthenticatedReadOnly,)
    queryset = CourseEntitlement.objects.all()
    serializer_class = SupportCourseEntitlementSerializer

    def filter_queryset(self, queryset):
        try:
            username_or_email = self.request.GET.get('user')
            user = User.objects.get(Q(username=username_or_email) | Q(email=username_or_email))
            queryset = queryset.filter(user=user)
            return super(EntitlementSupportView, self).filter_queryset(queryset).order_by('created')
        except (KeyError, User.DoesNotExist):
            return queryset.order_by('created')

    @method_decorator(require_support_permission)
    def update(self, request):
        """ Allows support staff to unexpire a user's entitlement."""
        support_user = request.user
        try:
            username_or_email = self.request.data['user']
            user = User.objects.get(Q(username=username_or_email) | Q(email=username_or_email))
        except User.DoesNotExist:
            return HttpResponseBadRequest(
                u'Could not find user {user}'.format(user=username_or_email)
            )
        try:
            course_uuid = request.data['course_uuid']
            reason = request.data['reason']
            comments = request.data.get('comments', None)
        except KeyError as err:
            return HttpResponseBadRequest(u'The field {} is required.'.format(text_type(err)))
        try:
            entitlement = CourseEntitlement.get_most_recent_entitlement(user=user, course_uuid=course_uuid)
        except CourseEntitlement.DoesNotExist:
            return HttpResponseBadRequest(
                u'Could not find entitlement to course {course_uuid} for user {user}'.format(
                    course_uuid=course_uuid, user=username_or_email
                )
            )
        if entitlement:
            if entitlement.expired_at is None:
                return HttpResponseBadRequest(
                    u"Entitlement for user {user} to course {course} is not expired.".format(
                        user=entitlement.user.username,
                        course=entitlement.course_uuid
                    )
                )
            if entitlement.enrollment_course_run is None:
                return HttpResponseBadRequest(
                    u"Entitlement for user {user} to course {course} has not been spent on a course run.".format(
                        user=entitlement.user.username,
                        course=entitlement.course_uuid
                    )
                )
            unenrolled_run = self.unexpire_entitlement(entitlement)
            CourseEntitlementSupportDetail.objects.create(
                entitlement=entitlement, reason=reason, comments=comments, unenrolled_run=unenrolled_run,
                support_user=support_user
            )
            return Response(
                status=status.HTTP_201_CREATED,
                data=SupportCourseEntitlementSerializer(instance=entitlement).data
            )
        else:
            return HttpResponseBadRequest(
                u'Could not find an entitlement for user {username} in course {course}'.format(
                    username=username_or_email,
                    course=course_uuid
                )
            )

    @method_decorator(require_support_permission)
    def create(self, request, *args, **kwargs):
        """ Allows support staff to grant a user a new entitlement for a course. """
        support_user = request.user
        try:
            username_or_email = self.request.data['user']
            user = User.objects.get(Q(username=username_or_email) | Q(email=username_or_email))
            course_uuid = request.data['course_uuid']
            reason = request.data['reason']
            comments = request.data.get('comments', None)
            mode = request.data.get('mode', 'verified')
        except KeyError as err:
            return HttpResponseBadRequest(u'The field {} is required.'.format(text_type(err)))
        except User.DoesNotExist:
            return HttpResponseBadRequest(
                u'Could not find user {username}.'.format(
                    username=username_or_email,
                )
            )
        entitlement = CourseEntitlement.objects.get_or_create(user=user, course_uuid=course_uuid, mode=mode)
        CourseEntitlementSupportDetail.objects.create(
            entitlement=entitlement, reason=reason, comments=comments, support_user=support_user
        )
        return Response(
            status=status.HTTP_201_CREATED,
            data=SupportCourseEntitlementSerializer(instance=entitlement).data
        )

    @staticmethod
    def unexpire_entitlement(entitlement):
        """
        Unenrolls a user from the run on which they have spent the given entitlement and
        sets the entitlement's expired_at date to null.
        """
        unenrolled_run = entitlement.enrollment_course_run.course
        entitlement.expired_at = None
        entitlement.enrollment_course_run.unenroll(skip_refund=True)
        entitlement.enrollment_course_run = None
        return unenrolled_run

"""
Support tool for changing and granting course entitlements
"""
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponseBadRequest
from edx_rest_framework_extensions.authentication import JwtAuthentication
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from six import text_type

from entitlements.api.v1.permissions import IsAdminOrAuthenticatedReadOnly
from entitlements.api.v1.serializers import SupportCourseEntitlementSerializer
from entitlements.models import CourseEntitlement, CourseEntitlementSupportDetail
from openedx.core.djangoapps.cors_csrf.authentication import SessionAuthenticationCrossDomainCsrf


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

    def update(self, request):
        """ Allows support staff to unexpire a user's entitlement."""
        support_user = request.user
        try:
            username_or_email = self.request.data['user']
            user = User.objects.get(Q(username=username_or_email) | Q(email=username_or_email))
            course_uuid = request.data['course_uuid']
            reason = request.data['reason']
            comments = request.data.get('comments', None)
            entitlement = self.get_most_recent_entitlement(user=user, course_uuid=course_uuid)
        except KeyError as err:
            return HttpResponseBadRequest(u'The field {} is required.'.format(text_type(err)))
        except (User.DoesNotExist, CourseEntitlement.DoesNotExist):
            return HttpResponseBadRequest(
                u'Could not find entitlement to course {course_uuid} for user {username}'.format(
                    course_uuid=course_uuid, username=username_or_email
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
        if CourseEntitlement.get_entitlement_if_active(user, course_uuid) is not None:
            return HttpResponseBadRequest(u'User {user} has an active entitlement in course {course}.'.format(
                user=username_or_email, course=course_uuid
            ))
        else:
            entitlement = CourseEntitlement.objects.create(user=user, course_uuid=course_uuid, mode=mode)
            CourseEntitlementSupportDetail.objects.create(
                entitlement=entitlement, reason=reason, comments=comments, support_user=support_user
            )
            return Response(
                status=status.HTTP_201_CREATED,
                data=SupportCourseEntitlementSerializer(instance=entitlement).data
            )

    @staticmethod
    def get_most_recent_entitlement(user, course_uuid):
        """
        Returns the most recently created entitlement for the given user in the given course.

        Args:
            user (User): user object record for which we are retrieving the entitlement.
            course_uuid (UUID): identified of the course for which we are retrieving the learner's entitlement.
        """
        return CourseEntitlement.objects.filter(user=user, course_uuid=course_uuid).latest('created')

    @staticmethod
    def unexpire_entitlement(entitlement):
        """
        Unenrolls a user from the run on which they have spent the given entitlement and
        sets the entitlement's expired_at date to null.
        """
        unenrolled_run = entitlement.enrollment_course_run.course
        entitlement.expired_at = None
        entitlement.enrollment_course_run.deactivate()
        entitlement.enrollment_course_run = None
        entitlement.save()
        return unenrolled_run

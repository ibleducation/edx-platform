"""
Support tool for changing and granting course entitlements
"""
from django.contrib.auth.models import User
from django.db import DatabaseError, transaction
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
from lms.djangoapps.support.decorators import require_support_permission
from openedx.core.djangoapps.cors_csrf.authentication import SessionAuthenticationCrossDomainCsrf
from student.models import CourseEnrollment

REQUIRED_CREATION_FIELDS = ['username_or_email', 'course_uuid', 'reason', 'mode']

class EntitlementSupportView(viewsets.ModelViewSet):
    """
    Allows viewing and changing learner course entitlements, used the support team.
    """
    authentication_classes = (JwtAuthentication, SessionAuthenticationCrossDomainCsrf,)
    permission_classes = (permissions.IsAuthenticated, IsAdminOrAuthenticatedReadOnly,)
    queryset = CourseEntitlement.objects.all()
    serializer_class = SupportCourseEntitlementSerializer

    def filter_queryset(self, queryset):
        username_or_email = self.request.GET.get('username_or_email', None)
        if username_or_email:
            try:
                user = User.objects.get(Q(username=username_or_email) | Q(email=username_or_email))
            except:
                return []
            queryset = queryset.filter(user=user)
            return super(EntitlementSupportView, self).filter_queryset(queryset).order_by('created')
        else:
            return []

    @method_decorator(require_support_permission)
    def list (self, request):
        return super(EntitlementSupportView, self).list(request)

    @method_decorator(require_support_permission)
    def update(self, request):
        """ Allows support staff to unexpire a user's entitlement."""
        support_user = request.user
        entitlement_uuid = request.data.get('entitlement_uuid')
        if not entitlement_uuid:
            return HttpResponseBadRequest(u'The field {fieldname} is required.'.format(fieldname='entitlement_uuid'))
        reason = request.data.get('reason')
        if not reason:
            return HttpResponseBadRequest(u'The field {fieldname} is required.'.format(fieldname='reason'))
        comments = request.data.get('comments', None)
        try:
            entitlement = CourseEntitlement.objects.get(uuid=entitlement_uuid)
        except CourseEntitlement.DoesNotExist:
            return HttpResponseBadRequest(
                u'Could not find entitlement {entitlement_uuid} for update'.format(
                    entitlement_uuid=entitlement_uuid
                )
            )
        if reason == CourseEntitlementSupportDetail.LEAVE_SESSION:
            return self._reinstate_entitlement(support_user, entitlement, comments)

    def _reinstate_entitlement(self, support_user, entitlement, comments):
        if entitlement.enrollment_course_run is None:
            return HttpResponseBadRequest(
                u"Entitlement {entitlement} has not been spent on a course run.".format(
                    entitlement=entitlement
                )
            )
        try:
            with transaction.atomic():
                unenrolled_run = self.unexpire_entitlement(entitlement)
                CourseEntitlementSupportDetail.objects.create(
                    entitlement=entitlement, reason=CourseEntitlementSupportDetail.LEAVE_SESSION, comments=comments,
                    unenrolled_run=unenrolled_run, support_user=support_user
                )
            return Response(
                status=status.HTTP_201_CREATED,
                data=SupportCourseEntitlementSerializer(instance=entitlement).data
            )
        except DatabaseError:
            return HttpResponseBadRequest(
                u'Failed to unexpire entitlement to course {course_uuid} for user {username_or_email}'.format(
                    course_uuid=course_uuid, username_or_email=username_or_email
                )
            )

    @method_decorator(require_support_permission)
    def create(self, request, *args, **kwargs):
        """ Allows support staff to grant a user a new entitlement for a course. """
        support_user = request.user
        comments = request.data.get('comments', None)

        creation_fields = {}
        missing_fields_string = ''
        for field in REQUIRED_CREATION_FIELDS:
            creation_fields[field] = request.data.get(field)
            if not creation_fields.get(field):
                missing_fields_string = missing_fields_string + ' ' + field
        if missing_fields_string:
            return HttpResponseBadRequest(
                u'The following required fields are missing from the request:{missing_fields}'.format(
                    missing_fields=missing_fields_string
                )
            )
        
        username_or_email = creation_fields['username_or_email']
        try:
            user = User.objects.get(Q(username=username_or_email) | Q(email=username_or_email))
        except User.DoesNotExist:
            return HttpResponseBadRequest(
                u'Could not find user {username_or_email}.'.format(
                    username_or_email=username_or_email,
                )
            )
        
        entitlement, _ = CourseEntitlement.objects.create(
            user=user, course_uuid=creation_fields['course_uuid'], mode=creation_fields['mode']
        )
        CourseEntitlementSupportDetail.objects.create(
            entitlement=entitlement, reason=creation_fields['reason'], comments=comments, support_user=support_user
        )
        return Response(
            status=status.HTTP_201_CREATED,
            data=SupportCourseEntitlementSerializer(instance=entitlement).data
        )

    @staticmethod
    def unexpire_entitlement(entitlement):
        """
        Unenrolls a user from the run in which they have spent the given entitlement and
        sets the entitlement's expired_at date to null.

        Returns:
            CourseOverview: course run from which the user has been unenrolled
        """
        unenrolled_run = entitlement.enrollment_course_run.course
        entitlement.expired_at = None
        CourseEnrollment.unenroll(
            user=entitlement.enrollment_course_run.user, course_id=unenrolled_run.id, skip_refund=True
        )
        entitlement.enrollment_course_run = None
        entitlement.save()
        return unenrolled_run

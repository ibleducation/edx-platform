"""
Completion utilities

"""

from django.conf import settings
from django.contrib.auth.models import User
from six import text_type

from lms.djangoapps.completion.models import BlockCompletion
from openedx.core.djangoapps.site_configuration.models import SiteConfiguration
from xmodule.modulestore.django import modulestore


def retrieve_last_block_completed_url(username):
    """
    From a string 'username' or object User retrieve
    the last course block marked as 'completed' and construct a URL

    :param username: str(username) or obj(User)
    :return: block_lms_url
    """
    if not isinstance(username, User):
        userobj = User.objects.get(username=username)
    else:
        userobj = username

    try:
        resume_block_key = BlockCompletion.get_last_sitewide_block_completed(userobj).block_key
    except AttributeError:
        print 'NO BLOCK'
        return

    item = modulestore().get_item(resume_block_key, depth=1)
    lms_base = SiteConfiguration.get_value_for_org(
        item.location.org,
        "LMS_BASE",
        settings.LMS_BASE
    )
    if not lms_base:
        print 'HERE'
        return

    return u"//{lms_base}/courses/{course_key}/jump_to/{location}".format(
        lms_base=lms_base,
        course_key=text_type(item.location.course_key),
        location=text_type(item.location),
    )

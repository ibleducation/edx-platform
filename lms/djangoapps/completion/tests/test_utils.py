"""
Test utils

"""

from __future__ import absolute_import, division, print_function, unicode_literals

from django.test import TestCase
from django.test.utils import override_settings

from lms.djangoapps.completion.test_utils import CompletionWaffleTestMixin
from lms.djangoapps.completion.utils import retrieve_last_block_completed_url
from student.models import CourseEnrollment
from student.tests.factories import UserFactory
from xmodule.modulestore.tests.django_utils import SharedModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory

from .. import models, waffle


class CompletionUtilsTestCase(SharedModuleStoreTestCase, CompletionWaffleTestMixin, TestCase):
    """
    Test completion utility functions
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a test course that can be used for non-destructive tests
        """
        # setUpClassAndTestData() already calls setUpClass on SharedModuleStoreTestCase
        with super(CompletionUtilsTestCase, cls).setUpClassAndTestData():
            cls._overrider = waffle.waffle().override(waffle.ENABLE_COMPLETION_TRACKING, True)
            cls._overrider.__enter__()  # pylint: disable=no-member
            cls.engaged_user = UserFactory.create()
            cls.cruft_user = UserFactory.create()
            cls.course = cls.create_test_course()
            cls.submit_faux_completions()
            cls.addCleanup(cls._overrider.__exit__, None, None, None)  # pylint: disable=no-member

    @classmethod
    def create_test_course(cls):
        """
        Creates a test course.
        """
        course = CourseFactory.create()
        with cls.store.bulk_operations(course.id):
            chapter = ItemFactory.create(category='chapter', parent_location=course.location)
            sequential = ItemFactory.create(category='sequential', parent_location=chapter.location)
            vertical1 = ItemFactory.create(category='vertical', parent_location=sequential.location)
            vertical2 = ItemFactory.create(category='vertical', parent_location=sequential.location)
        course.children = [chapter]
        chapter.children = [sequential]
        sequential.children = [vertical1, vertical2]

        if hasattr(cls, 'user_one'):
            CourseEnrollment.enroll(cls.engaged_user, course.id)
        if hasattr(cls, 'user_two'):
            CourseEnrollment.enroll(cls.cruft_user, course.id)
        return course

    @classmethod
    def submit_faux_completions(cls):
        """
        Submit completions (only for user_one)
        """
        for block in cls.course.children[0].children[0].children:
            models.BlockCompletion.objects.submit_completion(
                user=cls.engaged_user,
                course_key=cls.course.id,
                block_key=block.location,
                completion=1.0
            )

    @override_settings(LMS_BASE='test_url:9999')
    def test_retrieve_last_block_completed_url_user(self):
        """
        Test that the method returns a URL for the "last completed" block
        when sending a user object
        """
        block_url = retrieve_last_block_completed_url(self.engaged_user)
        empty_block_url = retrieve_last_block_completed_url(self.cruft_user)
        self.assertEqual(
            block_url,
            u'//test_url:9999/courses/org.0/course_0/Run_0/jump_to/i4x://org.0/course_0/vertical/vertical_4'
        )
        self.assertEqual(empty_block_url, None)

    @override_settings(LMS_BASE='test_url:9999')
    def test_retrieve_last_block_completed_url_username(self):
        """
        Test that the method returns a URL for the "last completed" block
        when sending a username
        """
        block_url = retrieve_last_block_completed_url(self.engaged_user.username)
        empty_block_url = retrieve_last_block_completed_url(self.cruft_user.username)
        self.assertEqual(
            block_url,
            u'//test_url:9999/courses/org.0/course_0/Run_0/jump_to/i4x://org.0/course_0/vertical/vertical_4'
        )
        self.assertEqual(empty_block_url, None)

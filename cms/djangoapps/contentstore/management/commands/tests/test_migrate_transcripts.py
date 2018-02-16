"""
Test for course transcript migration.
"""
import shutil
from tempfile import mkdtemp



from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory


class MigrateTranscripts(ModuleStoreTestCase):
    """
    Tests migrating video transcripts in courses from contentstore to S3
    """
    def setUp(self):
        """ Common setup. """
        super(MigrateTranscripts, self).setUp()
        self.store = modulestore()._get_modulestore_by_type(ModuleStoreEnum.Type.mongo)

        self.course1 = CourseFactory.create(
            org="test",
            course="course1",
            display_name="run1",
            default_store=ModuleStoreEnum.Type.mongo
        )
        chapter_course1 = ItemFactory.create(
            category='chapter',
            parent_location=self.course1.location,
            display_name='Test Chapter'
        )
        sequential_course1 = ItemFactory.create(
            category='sequential',
            parent_location=chapter_course1.location,
            display_name='Test Sequential'
        )
        vertical_course1 = ItemFactory.create(
            category='vertical',
            parent_location=sequential_course1.location,
            display_name='Test Vertical'
        )
        video_course1 = ItemFactory.create(
            category='video',
            parent_location=vertical_course1.location,
            display_name='Test Vertical'
        )
        self.course1_vertical_location = vertical_course1.location
        self.course1_video_location = video_course1.location

        self.course2 = CourseFactory.create(
            org="test",
            course="course2",
            display_name="run2",
            default_store=ModuleStoreEnum.Type.mongo
        )
        chapter_course2 = ItemFactory.create(
            category='chapter',
            parent_location=self.course2.location,
            display_name='Test Chapter'
        )
        sequential_course2 = ItemFactory.create(
            category='sequential',
            parent_location=chapter_course2.location,
            display_name='Test Sequential'
        )
        vertical_course2 = ItemFactory.create(
            category='vertical',
            parent_location=sequential_course2.location,
            display_name='Test Vertical'
        )
        video_course2 = ItemFactory.create(
            category='video',
            parent_location=vertical_course2.location,
            display_name='Test Vertical'
        )
        self.course2_vertical_location = vertical_course2.location
        self.course2_video_location = video_course2.location


    def test_migrate_transcripts(self):
        """
        Test migrating two courses
        """
        # check that both courses are migrated successfully
        courses, failed_export_courses = export_courses_to_output_path(self.temp_dir)
        self.assertEqual(len(courses), 2)
        self.assertEqual(len(failed_export_courses), 0)

        # manually make second course faulty and check that it fails on export
        second_course_id = self.second_course.id
        self.store.collection.update(
            {'_id.org': second_course_id.org, '_id.course': second_course_id.course, '_id.name': second_course_id.run},
            {'$set': {'metadata.tags': 'crash'}}
        )
        courses, failed_export_courses = export_courses_to_output_path(self.temp_dir)
        self.assertEqual(len(courses), 2)
        self.assertEqual(len(failed_export_courses), 1)
        self.assertEqual(failed_export_courses[0], unicode(second_course_id))

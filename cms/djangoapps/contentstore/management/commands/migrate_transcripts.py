"""
Command to migrate transcripts to S3.
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from opaque_keys import InvalidKeyError

from cms.djangoapps.contentstore.tasks import (
    DEFAULT_ALL_COURSES,
    DEFAULT_FORCE_UPDATE,
    enqueue_async_migrate_transcripts_tasks
)

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Example usage:
        $ ./manage.py cms migrate_transcripts --all-courses --settings=devstack_docker
        $ ./manage.py cms migrate_transcripts 'edX/DemoX/Demo_Course' --settings=devstack_docker
    """
    args = '<course_id course_id ...>'
    help = 'Migrates transcripts to S3 for one or more courses.'

    def add_arguments(self, parser):
        """
        Add arguments to the command parser.
        """
        parser.add_argument(
            '--all-courses', '--all',
            dest='all_courses',
            action='store_true',
            default=DEFAULT_ALL_COURSES,
            help=u'Migrates transcripts to S3 for all courses.',
        )
        parser.add_argument(
            '--force-update', '--force_update',
            action='store_true',
            default=DEFAULT_FORCE_UPDATE,
            help=u'Force migrate transcripts for the requested courses, overwrite if already present.',
        )
        parser.add_argument(
            '--routing-key',
            dest='routing_key',
            help=u'The celery routing key to use.'
        )

    def handle(self, *args, **options):
        if not options.get('all_courses') and len(args) < 1:
            raise CommandError('At least one course or --all-courses must be specified.')

        kwargs = {}
        for key in ('all_courses', 'force_update', 'routing_key'):
            if options.get(key):
                kwargs[key] = options[key]

        try:
            enqueue_async_migrate_transcripts_tasks(
                course_ids=args,
                **kwargs
            )
        except InvalidKeyError as exc:
            raise CommandError(u'Invalid Course Key: ' + unicode(exc))

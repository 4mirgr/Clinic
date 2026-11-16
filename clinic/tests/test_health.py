from unittest.mock import patch
from django.db import DatabaseError
from django.test import TestCase


class HealthTests(TestCase):
    def test_liveness_is_read_only_generic_and_not_indexed(self):
        response=self.client.get('/healthz')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,b'ok')
        self.assertEqual(response['Cache-Control'],'no-store')
        self.assertIn('noindex',response['X-Robots-Tag'])
        self.assertEqual(self.client.post('/healthz').status_code,405)

    def test_database_failure_does_not_disclose_the_connection(self):
        with patch('clinic.health.connection.cursor',side_effect=DatabaseError('synthetic-private-connection')):
            response=self.client.get('/healthz')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.content,b'unavailable')

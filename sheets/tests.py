from django.test import TransactionTestCase
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock
from sheets.models import SettingSheet, OcrJob
from sheets.tasks import execute_parallel_ocr_batch
from django.core.cache import cache
import tempfile
import os

from django.core.files.uploadedfile import SimpleUploadedFile

class ParallelOcrPipelineTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        User.objects.filter(username='testuser_parallel').delete()
        SettingSheet.objects.filter(sheet_code__in=['TEST-001', 'TEST-002', 'CODE-corr_tes']).delete()
        
        self.user = User.objects.create_user(username='testuser_parallel', password='password123')
        
        file1 = SimpleUploadedFile("test1.pdf", b"%PDF-1.4 test 1", content_type="application/pdf")
        file2 = SimpleUploadedFile("test2.pdf", b"%PDF-1.4 test 2", content_type="application/pdf")
        
        self.sheet1 = SettingSheet.objects.create(
            sheet_code="TEST-001",
            title="Phiếu Test 1",
            scan_file=file1,
            status='DRAFT',
            created_by=self.user
        )
        self.job1 = OcrJob.objects.create(
            sheet=self.sheet1,
            correlation_id="corr_test_001"
        )
        
        self.sheet2 = SettingSheet.objects.create(
            sheet_code="TEST-002",
            title="Phiếu Test 2",
            scan_file=file2,
            status='DRAFT',
            created_by=self.user
        )
        self.job2 = OcrJob.objects.create(
            sheet=self.sheet2,
            correlation_id="corr_test_002"
        )

    def tearDown(self):
        cache.clear()
        User.objects.filter(username='testuser_parallel').delete()
        SettingSheet.objects.filter(sheet_code__in=['TEST-001', 'TEST-002', 'CODE-corr_tes']).delete()

    @patch('sheets.tasks._run_ocr_cli')
    def test_parallel_batch_execution_success(self, mock_run_cli):
        # Giả lập kết quả trả về từ CLI
        def fake_run_cli(input_pdf, output_root, correlation_id, stage="all", device_mode="CPU"):
            if stage == "header":
                return 0, {
                    "status": "success",
                    "business": {
                        "page1_fields": {
                            "ticket_number": {"value": f"CODE-{correlation_id[:8]}"},
                            "station": {"value": "Trạm 220kV Test"},
                        }
                    },
                    "pages": [{"page_number": 1}, {"page_number": 2}]
                }, ""
            elif stage == "details":
                return 0, {
                    "status": "success",
                    "business": {
                        "setting_records": [
                            {"item_number": "1", "parameter_name": "I>", "value": "5.0"}
                        ]
                    },
                    "pages": [{"page_number": 3}]
                }, ""
            return 0, {}, ""

        mock_run_cli.side_effect = fake_run_cli

        result = execute_parallel_ocr_batch([self.job1.id, self.job2.id], user_id=self.user.id)
        self.assertIn("Processed batch of 2 OCR jobs", result)

        self.job1.refresh_from_db()
        self.sheet1.refresh_from_db()
        self.assertEqual(self.job1.status, "SUCCESS")
        self.assertEqual(self.sheet1.status, "ISSUED")
        self.assertEqual(len(self.sheet1.extracted_data), 1)
        self.assertEqual(self.sheet1.extracted_data[0]["parameter_name"], "I>")

        self.job2.refresh_from_db()
        self.sheet2.refresh_from_db()
        self.assertEqual(self.job2.status, "SUCCESS")
        self.assertEqual(self.sheet2.status, "ISSUED")
        self.assertEqual(len(self.sheet2.extracted_data), 1)


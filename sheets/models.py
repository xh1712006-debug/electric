from django.db import models
from stations.models import Relay

class SettingSheet(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued (Ready for Dispatch)'),
        ('TRANSFERRED', 'Transferred to Technician'),
        ('RECEIVED', 'Received by Technician'),
        ('PENDING_REVIEW', 'Pending Operation Approval'),
        ('COMPLETED', 'Completed'),
    )

    sheet_code = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='DRAFT')
    scan_file = models.FileField(upload_to='scans/')
    
    created_by = models.ForeignKey('auth.User', related_name='created_sheets', on_delete=models.SET_NULL, null=True)
    assigned_to = models.ForeignKey('auth.User', related_name='assigned_sheets', on_delete=models.SET_NULL, null=True, blank=True)
    supervisor_assigned = models.ForeignKey('auth.User', related_name='supervised_sheets', on_delete=models.SET_NULL, null=True, blank=True)
    
    relay = models.ForeignKey(Relay, on_delete=models.SET_NULL, null=True, blank=True)
    relay_text = models.CharField(max_length=255, null=True, blank=True)
    
    # OCR Data / Mock Data using JSONField of PostgreSQL
    extracted_data = models.JSONField(null=True, blank=True) 

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sheet_code} - {self.title}"

    class Meta:
        permissions = [
            ("can_view_stations", "Can view stations"),
            ("can_view_checks", "Can view periodic checks"),
            ("can_manage_users", "Can manage users & roles"),
            ("can_create_sheet", "Can create sheet and run OCR"),
            ("can_approve_sheet", "Can review and approve sheet"),
            ("can_dispatch_sheet", "Can dispatch sheet to technician"),
            ("can_execute_sheet", "Can execute sheet and sign (Technician)"),
            ("can_supervise_sheet", "Can supervise sheet and sign (Supervisor)"),
        ]

class SignatureRecord(models.Model):
    sheet = models.ForeignKey(SettingSheet, related_name='signatures', on_delete=models.CASCADE)
    signer_name = models.CharField(max_length=100)
    role = models.CharField(max_length=50)
    signed_at = models.DateTimeField(auto_now_add=True)
    signature_hash = models.CharField(max_length=256)

    def __str__(self):
        return f"{self.signer_name} ({self.role})"

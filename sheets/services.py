import uuid
import hashlib
from datetime import datetime

class MockEVNSignatureService:
    """
    Dịch vụ mô phỏng API Ký số EVN.
    """
    def initiate_signing_session(self, sheet_id, signer_role):
        """Mô phỏng việc khởi tạo phiên ký số."""
        session_id = f"EVN-MOCK-{uuid.uuid4().hex[:10].upper()}"
        signing_url = f"https://mock-sign.evn.com.vn/sign?session={session_id}"
        
        return {
            "success": True,
            "session_id": session_id,
            "signing_url": signing_url,
            "expires_in": 300
        }

    def confirm_signature(self, sheet, signer_name, signer_role):
        """Mô phỏng xác nhận ký số thành công."""
        raw_content = f"{sheet.sheet_code}_{signer_role}_{datetime.now().isoformat()}"
        signature_hash = hashlib.sha256(raw_content.encode('utf-8')).hexdigest()
        
        return {
            "success": True,
            "signature_hash": signature_hash,
            "signed_at": datetime.now(),
            "status": "SIGNED"
        }

# Khởi tạo singleton
evn_service = MockEVNSignatureService()

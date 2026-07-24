import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Kiểm tra xem user đã đăng nhập chưa
        if self.scope["user"].is_anonymous:
            await self.close()
            return
            
        # Khởi tạo danh sách các group
        self.groups_joined = []
        
        # Group name cho từng user dựa vào ID
        user_group = f"user_{self.scope['user'].id}"
        await self.channel_layer.group_add(user_group, self.channel_name)
        self.groups_joined.append(user_group)
        
        # Nếu là admin thì nhận thêm thông báo hệ thống (như autocheck)
        # Dùng sync_to_async để tránh lỗi SynchronousOnlyOperation
        user = self.scope['user']
        is_admin = await sync_to_async(
            lambda: user.is_superuser or user.groups.filter(name='ADMIN').exists()
        )()
        
        if is_admin:
            await self.channel_layer.group_add("autocheck_updates", self.channel_name)
            self.groups_joined.append("autocheck_updates")

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'groups_joined'):
            for group in self.groups_joined:
                try:
                    await self.channel_layer.group_discard(
                        group,
                        self.channel_name
                    )
                except Exception:
                    # Bỏ qua lỗi timeout khi Redis mất kết nối lúc disconnect
                    pass

    # Receive message from WebSocket (nếu FE có gửi lên, hiện tại không cần)
    async def receive(self, text_data):
        pass

    # Receive message from room group
    async def send_notification(self, event):
        message = event['message']
        title = event.get('title', 'Thông báo')
        type = event.get('type', 'info')

        try:
            # Gửi xuống WebSocket
            await self.send(text_data=json.dumps({
                'message': message,
                'title': title,
                'type': type
            }))
        except Exception:
            # Bỏ qua lỗi nếu kết nối đã đóng
            pass

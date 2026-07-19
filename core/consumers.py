import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Kiểm tra xem user đã đăng nhập chưa
        if self.scope["user"].is_anonymous:
            await self.close()
            return
            
        # Group name cho từng user dựa vào ID
        self.group_name = f"user_{self.scope['user'].id}"

        # Tham gia vào group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    # Receive message from WebSocket (nếu FE có gửi lên, hiện tại không cần)
    async def receive(self, text_data):
        pass

    # Receive message from room group
    async def send_notification(self, event):
        message = event['message']
        title = event.get('title', 'Thông báo')
        type = event.get('type', 'info')

        # Gửi xuống WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'title': title,
            'type': type
        }))

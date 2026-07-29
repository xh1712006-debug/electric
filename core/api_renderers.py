from rest_framework_xml.renderers import XMLRenderer

class CustomXMLRenderer(XMLRenderer):
    """
    Tùy chỉnh XML Renderer để bọc response vào chuẩn:
    <root>
        <success>true</success>
        <message>...</message>
        <data>...</data>
    </root>
    """
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get('response') if renderer_context else None
        
        is_success = True
        message = "Thành công"
        
        if response and response.status_code >= 400:
            is_success = False
            message = "Có lỗi xảy ra"
            if isinstance(data, dict) and 'detail' in data:
                message = str(data['detail'])

        wrapped_data = {
            'success': is_success,
            'message': message,
            'data': data
        }
        
        return super().render(wrapped_data, accepted_media_type, renderer_context)

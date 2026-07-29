import xml.etree.ElementTree as ET
from xml.dom import minidom

def json_to_xml(json_obj, root_tag='root'):
    """
    Chuyển đổi một đối tượng JSON (dict/list) thành chuỗi XML.
    """
    root = ET.Element(root_tag)
    
    def build_tree(parent, data):
        if isinstance(data, dict):
            for key, val in data.items():
                child = ET.SubElement(parent, key)
                build_tree(child, val)
        elif isinstance(data, list):
            for item in data:
                child = ET.SubElement(parent, 'item')
                build_tree(child, item)
        else:
            parent.text = str(data)

    build_tree(root, json_obj)
    
    # Prettify the XML
    xml_string = ET.tostring(root, encoding='utf-8')
    parsed_xml = minidom.parseString(xml_string)
    return parsed_xml.toprettyxml(indent="  ")

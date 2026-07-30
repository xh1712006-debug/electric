from django import template

register = template.Library()

@register.filter(name='has_group')
def has_group(user, group_name):
    if user.is_superuser:
        return True
    return user.groups.filter(name=group_name).exists()

@register.simple_tag(takes_context=True)
def url_replace(context, field, value):
    dict_ = context['request'].GET.copy()
    dict_[field] = value
    return dict_.urlencode()

from django import template

register = template.Library()

# @register.filter
# def get(dictionary, key):
#     """Retrieve a dictionary value safely."""
#     if isinstance(dictionary, dict):
#         return dictionary.get(key, None)
#     return None


@register.filter
def get(dictionary, key):
    """Safely retrieve a dictionary value by key."""
    if isinstance(dictionary, dict):
        # Return the actual value, or None if key doesn't exist
        return dictionary.get(key, None)
    return None
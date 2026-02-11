from django import template

register = template.Library()

# Full class names so Tailwind CLI scans and includes them.
TAG_COLOR_MAP = {
    "red": {"bg": "bg-red-900/40", "text": "text-red-300", "border": "border-red-700"},
    "orange": {"bg": "bg-orange-900/40", "text": "text-orange-300", "border": "border-orange-700"},
    "yellow": {"bg": "bg-yellow-900/40", "text": "text-yellow-300", "border": "border-yellow-700"},
    "green": {"bg": "bg-green-900/40", "text": "text-green-300", "border": "border-green-700"},
    "blue": {"bg": "bg-blue-900/40", "text": "text-blue-300", "border": "border-blue-700"},
    "indigo": {"bg": "bg-indigo-900/40", "text": "text-indigo-300", "border": "border-indigo-700"},
    "purple": {"bg": "bg-purple-900/40", "text": "text-purple-300", "border": "border-purple-700"},
    "pink": {"bg": "bg-pink-900/40", "text": "text-pink-300", "border": "border-pink-700"},
    "cyan": {"bg": "bg-cyan-900/40", "text": "text-cyan-300", "border": "border-cyan-700"},
    "gray": {"bg": "bg-gray-700/40", "text": "text-gray-300", "border": "border-gray-600"},
}

# Folder badge classes: bg-COLOR-900/30 text-COLOR-400
FOLDER_COLOR_MAP = {
    "red": {"bg": "bg-red-900/30", "text": "text-red-400"},
    "orange": {"bg": "bg-orange-900/30", "text": "text-orange-400"},
    "yellow": {"bg": "bg-yellow-900/30", "text": "text-yellow-400"},
    "green": {"bg": "bg-green-900/30", "text": "text-green-400"},
    "blue": {"bg": "bg-blue-900/30", "text": "text-blue-400"},
    "indigo": {"bg": "bg-indigo-900/30", "text": "text-indigo-400"},
    "purple": {"bg": "bg-purple-900/30", "text": "text-purple-400"},
    "pink": {"bg": "bg-pink-900/30", "text": "text-pink-400"},
    "cyan": {"bg": "bg-cyan-900/30", "text": "text-cyan-400"},
    "gray": {"bg": "bg-gray-700/30", "text": "text-gray-400"},
}

DEFAULT = {"bg": "bg-blue-900/40", "text": "text-blue-300", "border": "border-blue-700"}


@register.simple_tag
def tag_classes(color):
    """Return CSS classes dict for a tag color."""
    return TAG_COLOR_MAP.get(color, DEFAULT)


@register.simple_tag
def folder_classes(color):
    """Return CSS classes dict for a folder color."""
    return FOLDER_COLOR_MAP.get(color, {"bg": "bg-blue-900/30", "text": "text-blue-400"})

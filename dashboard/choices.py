from django.core.cache import cache

CACHE_KEY_PREFIX = "choice_options_"
CACHE_TIMEOUT = 3600  # 1 hour


def get_choices(category, include_inactive=False):
    """Return Django choice tuples for the given category from the DB."""
    cache_key = f"{CACHE_KEY_PREFIX}{category}_{'all' if include_inactive else 'active'}"
    result = cache.get(cache_key)
    if result is not None:
        return result

    from dashboard.models import ChoiceOption

    qs = ChoiceOption.objects.filter(category=category)
    if not include_inactive:
        qs = qs.filter(is_active=True)
    result = [(opt.value, opt.label) for opt in qs]
    cache.set(cache_key, result, CACHE_TIMEOUT)
    return result


def get_choice_label(category, value):
    """Return the display label for a value, falling back to the raw value."""
    if not value:
        return value
    choices = get_choices(category, include_inactive=True)
    for v, label in choices:
        if v == value:
            return label
    return value


def invalidate_choice_cache():
    """Clear all cached choice data."""
    from dashboard.models import CATEGORY_CHOICES

    for cat_value, _cat_label in CATEGORY_CHOICES:
        cache.delete(f"{CACHE_KEY_PREFIX}{cat_value}_active")
        cache.delete(f"{CACHE_KEY_PREFIX}{cat_value}_all")

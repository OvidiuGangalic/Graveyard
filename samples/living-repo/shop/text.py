from shop.norm_a import normalise as normalise_text
from shop.norm_b import normalise as normalise_scores


def slugify(text):
    return normalise_text(text).replace(" ", "-")


def rank(scores):
    return normalise_scores(scores)

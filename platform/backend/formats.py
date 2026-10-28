"""Small, hardware-bounded, exact aspect ratios; all sides divisible by 16."""
ASPECT_SIZES = {'1:1': (512, 512), '16:9': (768, 432), '9:16': (432, 768)}
SIZE_ASPECTS = {size: ratio for ratio, size in ASPECT_SIZES.items()}


def job_dimensions(job):
    width, height = job.get('width', 512), job.get('height', 512)
    if type(width) is not int or type(height) is not int or (width, height) not in SIZE_ASPECTS:
        raise ValueError('Unapproved image dimensions')
    return width, height

from ninja import ModelSchema, Router, Schema
from ninja_jwt.authentication import JWTAuth
from pydantic import HttpUrl

from .models import Link
from .utils import generate_short_code

router = Router(tags=["shorteners"])

# Input Schema
class ShortenRequest(Schema):
    original_url: HttpUrl

# Output Schema
class LinkSchema(ModelSchema):
    class Meta:
        model = Link
        exclude = ["id"]

@router.post("/shorten", response=LinkSchema, auth=JWTAuth())
def shorten_url(request, payload: ShortenRequest):
    # The endpoint is now protected by JWTAuth.
    # The authenticated user is available via request.user
    owner = request.user

    link = Link.objects.create(
        original_url=str(payload.original_url),
        short_code=generate_short_code(),
        owner=owner
    )
    return link

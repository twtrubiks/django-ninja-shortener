from shortener.api import router as shortener_router
from ninja_jwt.controller import NinjaJWTDefaultController
from ninja_extra import NinjaExtraAPI

api = NinjaExtraAPI(urls_namespace="shortener_api")
api.register_controllers(NinjaJWTDefaultController)

api.add_router("/", shortener_router)

from django.http import HttpResponse
from django.views import View


def index(request):
    return HttpResponse("welcome")


class OrderView(View):
    def get(self, request):
        return HttpResponse("orders")

    def post(self, request):
        return HttpResponse("created", status=201)

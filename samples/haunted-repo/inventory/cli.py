import sys

from inventory.models import Stock
from inventory.plugins import dispatch
from inventory.reports import build_report


def main():
    stock = Stock()
    stock.adjust("widget", 5)
    if len(sys.argv) > 2:
        print(dispatch(sys.argv[1], sys.argv[2]))
    print(build_report(stock.rows()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

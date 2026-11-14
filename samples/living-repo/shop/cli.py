import click

from shop.stock import Stock, factorial
from shop.tax import vat_rate
from shop.text import rank
from shop.helpers import *  # noqa: F403
from shop.dynamic import load, run_report


@click.command()
@click.option("--sku", default="A1")
def main(sku):
    stock = Stock()
    stock.adjust(sku)
    click.echo(f"{sku} vat={vat_rate('uk')} {shout(sku)}")  # noqa: F405
    click.echo(run_report("daily_report"))
    click.echo(run_report("weekly_report"))
    click.echo(f"{rank([1, 2])} {factorial(4)} {load('[1]')} {stock.value(2)}")


def run():
    main()


if __name__ == "__main__":
    run()

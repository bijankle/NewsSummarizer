"""Daily fact focused news digest: collect, filter, summarise, email, publish.

This package's top level must stay free of third party imports, because the
hourly schedule check (newsdigest.gate) runs before dependencies are installed.
"""

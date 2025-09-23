## Games Database

Code to combine existing DB with IGDB and consolidate.

### Schema

Eventual schema for schema

```yaml
game:
  dmc:
    title: string        # from MSU catalog
    edition: string      # edition/version info
    call_number: string? # optional, library call number
  igdb:
    title: string        # from IGDB API
    cover: string        # cover image URL/ID
    tags: [string]       # list of tags/genres
    summary: string      # game summary/description
    other: object?       # extra metadata (platforms, release year, etc.)
```
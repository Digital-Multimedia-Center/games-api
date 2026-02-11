## Games Database

Code to combine existing DB with IGDB and consolidate.

### Schema

Eventual schema for Database

```yaml
dmc-items:
  folio_id:
    title: string
    alternative_title: [string]
    authors: [string]
    edition: [string]
    platform: [string]
    platform_id_guess : int

enriched-items:
  igdb_id: int
  name: string
  cover:
    id: int
    image_id: string
  genres: [
    {
      id: int,
      name: string
    }
  ]
  summary: string
  game_type: int
  dmc_entries: [folio_id]
```

current error rate : 0.13
new error rate : 0.11

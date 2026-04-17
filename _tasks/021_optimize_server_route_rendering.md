# 021 Optimize Server Route Rendering

## Default Choice

Cache stable repository data and split context-building by panel before adding external caching services.

## Objective

Reduce backend time for small interactions and avoid rebuilding the full workspace context for panel-only actions.

## Acceptance Criteria

- Route timing is measurable.
- Stable Bible/source/chunk data is cached where safe.
- Panel endpoints build only the context they need.


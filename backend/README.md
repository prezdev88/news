# News Timeline Backend

Backend Java Spring Boot para registrar noticias/fechas con hashtags y fuentes.

## Requisitos
- Java 17
- Maven 3.9+
- Docker (para Postgres)

## Configuración
La app usa `application.properties` (sin YAML) con Postgres por defecto:
- URL: `jdbc:postgresql://localhost:5432/news`
- Usuario/clave: `news` / `news`
- Zona horaria: `America/Santiago`

### Base de datos con Docker
```bash
docker compose up -d  # levanta postgres y pgadmin
```

### Levantar stack completo (backend + front + postgres)
```bash
docker compose up -d --build
# front en http://localhost:4200 , backend en http://localhost:8080
```

### Ejecutar la aplicación
```bash
cd backend
mvn spring-boot:run
```

### Ejecutar tests
```bash
cd backend
mvn test
```

## API
Base path: `/api/v1`

### Crear entrada
```bash
curl -X POST http://localhost:8080/api/v1/entries \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2024-01-10",
    "headline": "Titular de prueba",
    "hashtags": ["kast", "venezuela"],
    "sources": [
      {"name": "Diario", "url": "https://ejemplo.com"},
      {"name": "Otro", "url": "https://otro.com", "position": 2}
    ]
  }'
```

### Listar entradas con filtros
- Por un hashtag (OR con múltiples):
```bash
curl "http://localhost:8080/api/v1/entries?hashtag=kast"
```
- Por varios hashtags (retorna entradas que tengan **al menos uno**):
```bash
curl "http://localhost:8080/api/v1/entries?hashtags=kast,boric"
```
- Por rango de fechas y texto (case-insensitive sobre headline):
```bash
curl "http://localhost:8080/api/v1/entries?from=2024-01-01&to=2024-12-31&q=venezuela"
```

### Obtener/actualizar/eliminar entrada
```bash
curl http://localhost:8080/api/v1/entries/{id}
curl -X PUT http://localhost:8080/api/v1/entries/{id} -H "Content-Type: application/json" -d '{...}'
curl -X DELETE http://localhost:8080/api/v1/entries/{id}
```

### Hashtags
- Listar existentes (opcional `q` para prefijo):
```bash
curl "http://localhost:8080/api/v1/hashtags"
curl "http://localhost:8080/api/v1/hashtags?q=ve"
```
- Detalle de un hashtag:
```bash
curl http://localhost:8080/api/v1/hashtags/kast
```

## Notas de implementación
- DTOs expuestos, entidades no se exponen.
- Hashtags se normalizan (trim, quita `#`, minúsculas, sin espacios, regex `[a-z0-9_-]{2,50}`); se crean automáticamente si no existen.
- Búsquedas usan filtros combinables (`from`, `to`, `q`, `hashtag`/`hashtags`). Múltiples hashtags se combinan con OR (MVP).
- Spring Data JPA + EntityGraph para evitar N+1 al cargar hashtags y sources.
- Flyway `V1__init.sql` crea tablas: `hashtag`, `news_entry`, `news_entry_hashtag`, `news_entry_source`.

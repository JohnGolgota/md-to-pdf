# Introducción

Esta API permite gestionar **clientes** y consultar su información. Todos los
recursos usan JSON y las fechas siguen ISO 8601. Esta es documentación ficticia.

- URL base: `https://api.ejemplo.com/v1`
- Codificación: UTF-8; admite nombres como *María Muñoz*.
- Revisá la sección [Errores](#errores) antes de integrar.

## Autenticación

Enviá un token de acceso en el encabezado `Authorization`.

```http
Authorization: Bearer TU_TOKEN
Content-Type: application/json
```

Nunca publiques credenciales reales en la documentación.

# Endpoints

## Crear un cliente

`POST /clientes`

| Campo | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| nombre | string | Sí | Nombre completo del cliente. |
| email | string | Sí | Correo único y válido. |
| activo | boolean | No | Su valor predeterminado es true. |

### Solicitud

```json
{
  "nombre": "María Muñoz",
  "email": "maria@example.com",
  "activo": true
}
```

### Respuesta · 201 Created

```json
{
  "id": "cli_123",
  "nombre": "María Muñoz",
  "email": "maria@example.com",
  "activo": true
}
```

## Consultar un cliente

`GET /clientes/{id}`

1. Obtené el identificador del cliente.
2. Enviá una solicitud autenticada.
3. Validá el código HTTP antes de interpretar la respuesta.

```sh
curl -H "Authorization: Bearer TU_TOKEN" https://api.ejemplo.com/v1/clientes/cli_123
```

# Errores

| Código | Motivo | Acción recomendada |
| --- | --- | --- |
| 400 | Datos inválidos | Verificá campos y tipos de la solicitud. |
| 401 | Token ausente o vencido | Renovación del token de acceso. |
| 404 | Cliente inexistente | Comprobá el identificador del recurso. |
| 429 | Límite de solicitudes | Esperá antes de reintentar. |

```json
{
  "error": "cliente_no_encontrado",
  "message": "No se encontró el cliente solicitado."
}
```

# Versionado

Los cambios incompatibles se publican en una nueva versión de la URL base.
Consultá [HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) para el
significado de los códigos de estado.

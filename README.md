# Solucion.ar — Backend

> Plataforma marketplace de servicios end-to-end | Trabajo Final de Ingeniería (TFI)

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![SQLModel](https://img.shields.io/badge/SQLModel-latest-009688?style=for-the-badge)
![Alembic](https://img.shields.io/badge/Alembic-migrations-red?style=for-the-badge)
![JWT](https://img.shields.io/badge/JWT-OAuth2-black?style=for-the-badge&logo=jsonwebtokens)

---

## 📋 Descripción

**Solucion.ar** es una plataforma marketplace que conecta clientes con proveedores de servicios. Este repositorio contiene el backend completo desarrollado con **FastAPI** como proyecto final de la carrera de Ingeniería en Sistemas de Información (UAI, 2025).

El sistema cubre el ciclo completo: registro y autenticación de usuarios y proveedores, publicación de servicios, gestión de reservas, sistema de reseñas y flujo de pagos con simulación de webhooks.

---

## 🏗️ Arquitectura

El backend está organizado con una **arquitectura modular por dominio**, separando responsabilidades en routers, esquemas Pydantic y capa de base de datos:

```
Solucionar-BackEnd/
│
├── main.py               # Entry point, configuración de la app y CORS
├── database.py           # Conexión a PostgreSQL con SQLModel/SQLAlchemy
│
├── core/                 # Lógica central y utilidades
│   ├── security.py       # JWT, hashing de contraseñas (passlib)
│   ├── dependencies.py   # Dependencias reutilizables (get_current_user, etc.)
│   └── config.py         # Variables de entorno con Pydantic Settings
│
├── routers/              # Endpoints organizados por dominio
│   ├── auth.py           # Registro, login, perfil
│   ├── services.py       # CRUD de servicios/publicaciones
│   ├── bookings.py       # Reservas y gestión de estados
│   ├── reviews.py        # Reseñas de servicios
│   └── payments.py       # Flujo de pago con adapter pattern
│
├── schema/               # Modelos SQLModel (DB) y Pydantic (request/response)
│   ├── user.py
│   ├── service.py
│   ├── booking.py
│   ├── review.py
│   └── payment.py
│
└── alembic/              # Migraciones de base de datos
    └── versions/
```

---

## ⚙️ Stack Técnico

| Categoría | Tecnología |
|---|---|
| Framework | FastAPI |
| ORM / Modelos | SQLModel + SQLAlchemy |
| Base de datos | PostgreSQL |
| Migraciones | Alembic |
| Validación | Pydantic v2 |
| Autenticación | JWT + OAuth2 (python-jose + passlib) |
| Servidor ASGI | Uvicorn |
| Documentación | Swagger/OpenAPI (integrado) |

---

## 🚀 Instalación y ejecución local

### Prerrequisitos

- Python 3.11+
- PostgreSQL corriendo localmente o en la nube
- Git

### 1. Clonar el repositorio

```bash
git clone https://github.com/FacundoKinderknecht/Solucionar-BackEnd.git
cd Solucionar-BackEnd
```

### 2. Crear entorno virtual e instalar dependencias

```bash
python -m venv venv
source venv/bin/activate       # Linux/Mac
venv\Scripts\activate          # Windows

pip install -r requirements.txt
```

### 3. Configurar variables de entorno

Crear un archivo `.env` en la raíz del proyecto:

```env
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DBNAME
SECRET_KEY=tu-clave-secreta-muy-segura
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

### 4. Ejecutar migraciones

```bash
alembic upgrade head
```

### 5. Correr el servidor

```bash
uvicorn main:app --reload
```

La API estará disponible en `http://localhost:8000`
La documentación interactiva en `http://localhost:8000/docs`

---

## 📡 Endpoints principales

### 🔐 Autenticación (`/auth`)

| Método | Endpoint | Descripción | Auth |
|---|---|---|---|
| `POST` | `/auth/register` | Registro de nuevo usuario/proveedor | ❌ |
| `POST` | `/auth/login` | Login con OAuth2 Form → devuelve JWT | ❌ |
| `GET` | `/auth/me` | Datos del usuario autenticado | ✅ |

### 📦 Servicios (`/services`)

| Método | Endpoint | Descripción | Auth |
|---|---|---|---|
| `GET` | `/services` | Listado de servicios disponibles | ❌ |
| `GET` | `/services/{id}` | Detalle de un servicio | ❌ |
| `POST` | `/services` | Crear publicación (proveedor) | ✅ |
| `PUT` | `/services/{id}` | Editar publicación | ✅ |
| `DELETE` | `/services/{id}` | Eliminar publicación | ✅ |

### 📅 Reservas (`/bookings`)

| Método | Endpoint | Descripción | Auth |
|---|---|---|---|
| `POST` | `/bookings` | Crear reserva (cliente) | ✅ |
| `GET` | `/bookings/my` | Reservas del usuario autenticado | ✅ |
| `PATCH` | `/bookings/{id}/status` | Cambiar estado (pendiente/confirmada/cancelada) | ✅ |

### ⭐ Reseñas (`/reviews`)

| Método | Endpoint | Descripción | Auth |
|---|---|---|---|
| `POST` | `/reviews` | Crear reseña de un servicio | ✅ |
| `GET` | `/reviews/{service_id}` | Reseñas de un servicio | ❌ |

### 💳 Pagos (`/payments`)

| Método | Endpoint | Descripción | Auth |
|---|---|---|---|
| `POST` | `/payments/initiate` | Iniciar pago (adapter pattern) | ✅ |
| `POST` | `/payments/webhook` | Recibir callback del gateway | ❌ |
| `GET` | `/payments/{booking_id}` | Estado del pago de una reserva | ✅ |

---

## 🔑 Características destacadas

- **Patrón Adapter para pagos**: arquitectura extensible que normaliza distintos gateways de pago con una interfaz común, con simulación de webhooks y callbacks
- **JWT/OAuth2**: autenticación stateless con tokens de acceso, roles diferenciados entre cliente y proveedor
- **Migraciones Alembic**: control de versiones del esquema de base de datos
- **Documentación automática**: Swagger UI disponible en `/docs`, ReDoc en `/redoc`
- **CORS configurado**: preparado para consumo desde el frontend en cualquier origen durante desarrollo

---

## 🔗 Repositorio Frontend

El frontend de esta aplicación se encuentra en:
[Solucionar-FrontEnd](https://github.com/FacundoKinderknecht/Solucionar-FrontEnd)

---

## 👤 Autor

**Facundo Kinderknecht**
[LinkedIn](https://linkedin.com/in/facundo-kinderknecht) · [GitHub](https://github.com/FacundoKinderknecht)

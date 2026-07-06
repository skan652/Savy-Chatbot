# SAVY Tax Assistant API Documentation

## Overview

The SAVY Tax Assistant API provides endpoints for tax assessment, refund estimation, and conversation management. This API powers the SAVY Tax Assessment Bot which helps users determine their eligibility for tax refunds and identify tax-saving opportunities.

**Base URL:** `http://localhost:5000`

**Authentication:** JWT Bearer token (optional for most endpoints, but required for some)

## Interactive Documentation

The API documentation is available through Swagger UI at:
- **Swagger UI:** `/apidocs/`
- **Raw OpenAPI Spec:** `/swagger_spec`

---

## Authentication Endpoints

### 1. Login with Email
**POST** `/api/auth/email/login`

Authenticate a user with email and password.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "password123"
}
# Admin Functionality

This document describes the admin functionality that has been migrated from the Flask app to the new React + FastAPI solution.

## Overview

Admin functionality provides system-wide administrative capabilities for managing users and monitoring system statistics. Only users listed in the `AICT_OMNIADMINS` environment variable can access these features.

## Configuration

### Environment Variables

Set the `AICT_OMNIADMINS` environment variable with a comma-separated list of admin email addresses:

```bash
AICT_OMNIADMINS=admin1@example.com,admin2@example.com
```

### Backend Setup

The admin functionality is automatically available when the environment variable is set. No additional configuration is required.

## Features

### 1. User Management (`/admin/users`)

**Access**: Only omniadmins can access this page.

**Features**:
- **List Users**: View all users in the system with pagination
- **Search Users**: Search users by name or email
- **User Details**: View detailed user information including:
  - User ID, email, name
  - Number of owned apps
  - Number of API keys
  - Account status (active/inactive)
  - Creation date
- **Delete Users**: Remove users and all associated data (with confirmation)

**API Endpoints**:
- `GET /internal/admin/users` - List users with pagination and search
- `GET /internal/admin/users/{user_id}` - Get user details
- `DELETE /internal/admin/users/{user_id}` - Delete user

### 2. System Statistics (`/admin/stats`)

**Access**: Only omniadmins can access this page.

**Features**:
- **Overview Cards**: 
  - Total users count
  - Total apps count
  - Total agents count
  - Total API keys count
- **Detailed Statistics**:
  - API keys breakdown (active vs inactive)
  - User activity metrics
  - Recent users (last 30 days)
- **Recent Users Table**: List of users who joined in the last 30 days

**API Endpoints**:
- `GET /internal/admin/stats` - Get system-wide statistics

## Navigation

Admin users will see an "Admin" section in the sidebar with:
- **Users** - Link to user management page
- **Stats** - Link to system statistics page

Regular users will not see the admin section at all.

## Authentication

Admin functionality uses the same Google OAuth authentication as the rest of the application. The admin status is checked by verifying if the user's email is in the `AICT_OMNIADMINS` list.

## Security

- Admin access is controlled by the `AICT_OMNIADMINS` environment variable
- All admin endpoints require authentication
- Admin status is verified on every request
- User deletion requires confirmation
- All admin actions are logged

## Migration Notes

This functionality was migrated from the original Flask app where it was available at:
- `/admin/users` - User management
- `/admin/stats` - System statistics

The new implementation maintains the same functionality while providing a modern React interface and FastAPI backend.

## Troubleshooting

### Admin section not visible
1. Check that your email is in the `AICT_OMNIADMINS` environment variable
2. Ensure the environment variable is properly set and the backend is restarted
3. Verify that you're logged in with the correct email address

### Admin endpoints returning 403
1. Verify the `AICT_OMNIADMINS` environment variable is set correctly
2. Check that your email is in the comma-separated list
3. Ensure there are no extra spaces in the email addresses

### User deletion fails
1. Check that the user exists
2. Verify database permissions
3. Check application logs for detailed error messages 
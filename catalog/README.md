# **CatalogService API Documentation**

## **Overview**

The **CatalogService** is a RESTful API built with CherryPy, designed to manage devices, rooms, and users in a smart environment. It supports CRUD (Create, Read, Update, Delete) operations and ensures data consistency across its components.

---

## **Endpoints**

### **1. Broker**

#### **GET /broker**

-   **Description**: Retrieve broker configuration details.
-   **Response**:
    ```json
    {
        "ip": "192.168.1.1",
        "port": 1883
    }
    ```

---

### **2. Devices**

#### **GET /devices**

-   **Description**: Retrieve all devices.
-   **Response**:
    ```json
    [
        {
            "deviceID": "1234-uuid",
            "ip": "192.168.1.10",
            "port": 8080,
            "endpoints": {
                "mqtt": { "topics": ["buildingA/1/A101/aqi"] },
                "rest": { "restIP": "http://192.168.1.10:8080" }
            },
            "availableResources": ["temperature"],
            "roomID": "room-uuid",
            "insert-timestamp": "2024-01-01T12:00:00"
        }
    ]
    ```

#### **GET /devices/{deviceID}**

-   **Description**: Retrieve a specific device by ID.

#### **POST /devices**

-   **Description**: Add a new device.
-   **Request Body**:
    ```json
    {
        "ip": "192.168.1.20",
        "port": 8080,
        "endpoints": {
            "mqtt": { "topics": ["/buildingA/1/101/aqi"] }, // "{building}/{floor}/{room}/aqi"
            "rest": { "restIP": "http://192.168.1.20:8080" }
        },
        "availableResources": ["humidity"],
        "roomID": "room-uuid"
    }
    ```

#### **PUT /devices/{deviceID}**

-   **Description**: Update an existing device by ID.
-   **Request Body**: Same as POST.

#### **DELETE /devices/{deviceID}**

-   **Description**: Remove a device by ID.

---

### **3. Rooms**

#### **GET /rooms**

-   **Description**: Retrieve all rooms.
-   **Response**:
    ```json
    [
        {
            "roomID": "room-uuid",
            "number": "A101",
            "floor": 1,
            "buildingName": "Main Building",
            "openingHours": { "start": "08:00", "end": "18:00" },
            "coordinates": { "lat": 45.07, "lon": 7.67 },
            "devices": ["1234-uuid"]
        }
    ]
    ```

#### **GET /rooms/{roomID}**

-   **Description**: Retrieve a specific room by ID.

#### **POST /rooms**

-   **Description**: Add a new room.
-   **Request Body**:
    ```json
    {
        "number": "A102",
        "floor": 1,
        "buildingName": "A",
        "openingHours": { "start": "08:00", "end": "18:00" },
        "coordinates": { "lat": 45.07, "lon": 7.67 }
    }
    ```

#### **PUT /rooms/{roomID}**

-   **Description**: Update an existing room.
-   **Request Body**: Same as POST with added `"devices"` field.

#### **DELETE /rooms/{roomID}**

-   **Description**: Remove a room and its associated devices.

---

### **4. Users**

#### **GET /users**

-   **Description**: Retrieve all users.
-   **Response**:
    ```json
    [
        {
            "userID": "user-uuid",
            "username": "JohnDoe101",
            "telegramChatID": "123456",
            "rooms": ["room-uuid"]
        }
    ]
    ```

#### **GET /users/{userID}**

-   **Description**: Retrieve a specific user by ID.

#### **POST /users**

-   **Description**: Add a new user.
-   **Request Body**:
    ```json
    {
        "username": "JohnDoe101",
        "telegramChatID": "654321",
        "rooms": ["room-uuid"]
    }
    ```

#### **PUT /users/{userID}**

-   **Description**: Update an existing user.
-   **Request Body**: Same as POST.

#### **DELETE /users/{userID}**

-   **Description**: Remove a user by ID.

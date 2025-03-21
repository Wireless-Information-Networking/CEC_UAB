local function read_csv(file_path)
    local csv_file = io.open(file_path, "r")
    if not csv_file then
        ngx.log(ngx.ERR, "Failed to open CSV file: ", file_path)
        return {}
    end

    local api_keys = {}
    for line in csv_file:lines() do
        local id, key, name = line:match("([^,]+),([^,]+),([^,]+)")
        if id and key and name then
            api_keys[key] = true
        end
    end

    csv_file:close()
    return api_keys
end

-- Validate the HTTP Method
if ngx.req.get_method() ~= "POST" then
    ngx.status = ngx.HTTP_NOT_ALLOWED
    ngx.header.content_type = "application/json"
    ngx.say('{"error": "Method Not Allowed", "message": "Only POST requests are allowed"}')
    return ngx.exit(ngx.HTTP_NOT_ALLOWED)
end

-- Load API keys from CSV
local api_keys = read_csv("/etc/nginx/auth_keys.csv")

-- Validate the API-Key header
local api_key = ngx.req.get_headers()["API-Key"]
if not api_key or not api_keys[api_key] then
    ngx.status = ngx.HTTP_FORBIDDEN
    ngx.header.content_type = "application/json"
    ngx.say('{"error": "Unauthorized", "message": "Missing or invalid API Key"}')
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end

-- Validate the Content-Type header
local content_type = ngx.req.get_headers()["Content-Type"]
if not content_type or not string.find(content_type, "application/json") then
    ngx.status = 415
    ngx.header.content_type = "application/json"
    ngx.say('{"error": "Unsupported Media Type", "message": "Content-Type must be application/json"}')
    return ngx.exit(415)
end

-- Validate the JSON body
ngx.req.read_body() -- Read the request body
local body = ngx.req.get_body_data()

if not body or body == "" then
    ngx.status = 400
    ngx.header.content_type = "application/json"
    ngx.say('{"error": "Bad Request", "message": "JSON body is empty"}')
    return ngx.exit(400)
end

-- Check if the JSON is valid and not empty
local cjson = require "cjson.safe"
local decoded_body = cjson.decode(body)

if not decoded_body or next(decoded_body) == nil then
    ngx.status = 400
    ngx.header.content_type = "application/json"
    ngx.say('{"error": "Bad Request", "message": "JSON body is empty or invalid"}')
    return ngx.exit(400)
end

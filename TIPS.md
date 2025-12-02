# Deobfuscation Tips & Strategies

This document provides strategies for improving the Mock Environment and debugging cases where the deobfuscator fails to decrypt strings or extract URLs.

## 1. Handling "Silent Failures" (No Decryption)

If a script runs but produces no output (no decrypted strings, no URLs), it is likely detecting the fake environment and aborting execution silently.

### **Strategy: Mimic Standard Lua Behavior**
*   **Problem:** Returning a dummy table for *everything* allows scripts to easily detect the environment. For example, `if some_random_variable then ... end` will be true if you return a dummy object, but `false`/`nil` in a real environment.
*   **Solution:** Change the `__index` metamethod of your global mock environment to return `nil` for unknown globals instead of a dummy object.
    ```lua
    __index = function(t, k)
        -- ... check known globals ...
        print("ACCESSED (NIL) --> " .. k) -- Log this!
        return nil
    end
    ```

### **Strategy: Mock `type()` and `typeof()`**
*   **Problem:** Scripts often check `type(game)` or `typeof(workspace)`. If your dummy object returns "table" instead of "userdata" or "Instance", the script knows it's being emulated.
*   **Solution:** Override `type` and `typeof` to check for your dummy objects.
    ```lua
    local real_type = type
    local function type(v)
        local mt = getmetatable(v)
        if mt and mt.__is_mock_dummy then
            return "userdata" -- or appropriate type
        end
        return real_type(v)
    end
    ```

## 2. Extracting Hidden URLs (`HttpGet`)

Scripts often use `game:HttpGet(url)` to load external payloads.

### **Strategy: Function Hooking**
*   **Problem:** The URL is passed as an argument, but if you just return a dummy result for `game.HttpGet`, you might miss the argument if you aren't logging call arguments explicitly or if the logging is flooded.
*   **Solution:** Specifically check for `HttpGet` in your `__index` handler and return a specialized function that logs the URL.
    ```lua
    if k == "HttpGet" or k == "HttpGetAsync" then
         return function(_, url, ...)
             print("URL DETECTED --> " .. tostring(url))
             return create_dummy("HttpGetResult")
                 end
            end
    ```

## 3. Detecting "Canary" Checks

Obfuscators often access random, non-existent variables (e.g., `BxkNtTSjdExrM`) to see if the environment returns `nil` (correct) or something else (incorrect).

*   **Tip:** Watch your logs. If you see accesses to random strings like `ACCESSED (NIL) --> BxkNtTSjdExrM`, and then the script stops, it's likely a canary check. Ensure your environment returns `nil` for these.

## 4. Infinite Loops on Missing Globals

Sometimes, a script will enter an infinite loop waiting for a variable to be defined.

*   **Tip:** If the trace shows repetitive access to the same NIL variable (e.g., `ACCESSED (NIL) --> SomeVar` repeated 100+ times), the script is likely waiting for it.
*   **Solution:** In such cases, you may need to explicitly whitelist that variable in `deobfuscator.py` to return a dummy object instead of `nil`. However, be careful not to whitelist "canary" variables.

## 5. Property-Specific Mocks

Some scripts check specific properties, e.g., `game.PlaceId`.

*   **Tip:** If execution stops after accessing a specific property (e.g., `ACCESSED --> game.PlaceId`), the script might be doing `if game.PlaceId == 1234 then ...`.
*   **Solution:** modify the Mock Environment to return specific values for these keys.
    ```lua
    if k == "PlaceId" then return 123456 end
    ```

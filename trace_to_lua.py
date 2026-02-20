import os
import sys

def parse_trace(report_file):
    with open(report_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    lua_code = []
    indent = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("CALL_RESULT -->"):
            code = line.split("CALL_RESULT -->")[1].strip()
            # clean up variable names
            code = code.replace("game_GetService_", "Service_")
            lua_code.append(("    " * indent) + code)
            
        elif line.startswith("SET GLOBAL -->"):
            code = line.split("SET GLOBAL -->")[1].strip()
            lua_code.append(("    " * indent) + code)
            
        elif line.startswith("TRACE_PRINT -->"):
            code = line.split("TRACE_PRINT -->")[1].strip()
            lua_code.append(("    " * indent) + f'print("{code}")')
            
        elif line.startswith("URL DETECTED -->"):
            url = line.split("URL DETECTED -->")[1].strip()
            lua_code.append(("    " * indent) + f'-- URL DETECTED: {url}')
            
        elif line.startswith("--- ENTERING CLOSURE FOR"):
            func_name = line.replace("--- ENTERING CLOSURE FOR ", "").replace(" ---", "").strip()
            lua_code.append(("    " * indent) + f"-- INSIDE CLOSURE: {func_name}")
            indent += 1
            
        elif line.startswith("--- EXITING CLOSURE FOR"):
            indent = max(0, indent - 1)
            lua_code.append(("    " * indent) + f"-- END CLOSURE")
            
    # Write to a new file
    out_file = report_file.replace(".report.txt", ".deobf.lua")
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write("-- Deobfuscated via Trace Emulation\n\n")
        f.write("\n".join(lua_code))
        
    print(f"Saved {out_file}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        parse_trace(sys.argv[1])
    else:
        for file in os.listdir("obfuscated_scripts"):
            if file.endswith(".report.txt"):
                parse_trace(os.path.join("obfuscated_scripts", file))

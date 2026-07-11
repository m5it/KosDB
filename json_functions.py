"""
JSON Functions Module for KosDB v3.2.0

Provides JSON data type support, validation, extraction operators,
and utility functions for working with JSON data.
"""

import json
import re
from typing import Any, Dict, List, Optional, Union


class JSONError(Exception):
    """Exception for JSON-related errors."""
    pass


def validate_json(value: Any) -> bool:
    """
    Validate if a value is valid JSON.
    
    Args:
        value: Value to validate (can be string or parsed JSON)
    
    Returns:
        True if valid JSON, False otherwise
    """
    if value is None:
        return True
    
    # If it's already a dict or list, it's valid JSON
    if isinstance(value, (dict, list)):
        return True
    
    # If it's a string, try to parse it
    if isinstance(value, str):
        try:
            json.loads(value)
            return True
        except (json.JSONDecodeError, TypeError):
            return False
    
    # Numbers, booleans are also valid
    if isinstance(value, (int, float, bool)):
        return True
    
    return False


def parse_json(value: Any) -> Any:
    """
    Parse a JSON value.
    
    Args:
        value: JSON string or Python object
    
    Returns:
        Parsed JSON object
    
    Raises:
        JSONError: If value is not valid JSON
    """
    if value is None:
        return None
    
    # Already parsed
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    
    # Parse string
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            raise JSONError(f"Invalid JSON: {e}")
    
    raise JSONError(f"Cannot parse JSON from type {type(value)}")


def json_extract(json_data: Any, path: str) -> Any:
    """
    Extract value from JSON using path expression.
    
    Supports MySQL-style JSON path syntax:
    - $.key for object keys
    - $.key1.key2 for nested keys
    - $[0] for array elements
    - $[*] for all array elements (returns list)
    
    Args:
        json_data: JSON data (string or parsed)
        path: JSON path expression
    
    Returns:
        Extracted value or None if path not found
    
    Examples:
        json_extract('{"a": 1}', '$.a') -> 1
        json_extract('{"a": {"b": 2}}', '$.a.b') -> 2
        json_extract('[1, 2, 3]', '$[0]') -> 1
    """
    try:
        data = parse_json(json_data)
    except JSONError:
        return None
    
    if not path.startswith('$'):
        path = '$' + path
    
    # Parse path components
    components = _parse_json_path(path)
    
    # Traverse data
    result = data
    for comp in components:
        if result is None:
            return None
        
        if isinstance(comp, int):
            # Array index
            if isinstance(result, list):
                if comp < len(result):
                    result = result[comp]
                else:
                    return None
            else:
                return None
        elif comp == '*':
            # Wildcard - return all elements
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return list(result.values())
            else:
                return None
        else:
            # Object key
            if isinstance(result, dict):
                result = result.get(comp)
            else:
                return None
    
    return result


def json_extract_text(json_data: Any, path: str) -> Optional[str]:
    """
    Extract value as text (unquoted string).
    
    Similar to ->> operator in MySQL.
    
    Args:
        json_data: JSON data
        path: JSON path expression
    
    Returns:
        String representation of value, or None
    """
    value = json_extract(json_data, path)
    if value is None:
        return None
    
    if isinstance(value, str):
        return value
    
    # Convert to JSON string for other types
    return json.dumps(value)


def json_contains(json_data: Any, candidate: Any, path: Optional[str] = None) -> bool:
    """
    Check if JSON contains a specific value.
    
    Args:
        json_data: JSON data to search
        candidate: Value to search for (will be converted to JSON)
        path: Optional path to search within
    
    Returns:
        True if candidate is found in json_data
    
    Examples:
        json_contains('{"a": 1, "b": 2}', 1) -> True
        json_contains('{"a": [1, 2, 3]}', 2, '$.a') -> True
    """
    try:
        data = parse_json(json_data)
        candidate_json = json.dumps(parse_json(candidate))
    except JSONError:
        return False
    
    if path:
        data = json_extract(data, path)
        if data is None:
            return False
    
    # Convert data to JSON string for comparison
    def search_recursive(obj: Any) -> bool:
        if json.dumps(obj) == candidate_json:
            return True
        
        if isinstance(obj, dict):
            for v in obj.values():
                if search_recursive(v):
                    return True
        elif isinstance(obj, list):
            for item in obj:
                if search_recursive(item):
                    return True
        
        return False
    
    return search_recursive(data)


def json_contains_path(json_data: Any, path: str) -> bool:
    """
    Check if JSON path exists in data.
    
    Args:
        json_data: JSON data
        path: JSON path expression
    
    Returns:
        True if path exists
    """
    return json_extract(json_data, path) is not None


def json_keys(json_data: Any, path: Optional[str] = None) -> Optional[List[str]]:
    """
    Get keys from JSON object.
    
    Args:
        json_data: JSON data
        path: Optional path to object
    
    Returns:
        List of keys, or None if not an object
    """
    try:
        data = parse_json(json_data)
    except JSONError:
        return None
    
    if path:
        data = json_extract(data, path)
    
    if isinstance(data, dict):
        return list(data.keys())
    
    return None


def json_array_length(json_data: Any, path: Optional[str] = None) -> Optional[int]:
    """
    Get length of JSON array.
    
    Args:
        json_data: JSON data
        path: Optional path to array
    
    Returns:
        Length of array, or None if not an array
    """
    try:
        data = parse_json(json_data)
    except JSONError:
        return None
    
    if path:
        data = json_extract(data, path)
    
    if isinstance(data, list):
        return len(data)
    
    return None


def json_array_append(json_data: Any, path: str, value: Any) -> Any:
    """
    Append value to JSON array.
    
    Args:
        json_data: Original JSON data
        path: Path to array
        value: Value to append
    
    Returns:
        Modified JSON data
    """
    data = parse_json(json_data)
    
    if not path.startswith('$'):
        path = '$' + path
    
    components = _parse_json_path(path)
    
    # Navigate to parent of target
    target = data
    for comp in components[:-1]:
        if isinstance(comp, int):
            target = target[comp]
        else:
            target = target[comp]
    
    # Append to target array
    last_comp = components[-1]
    if isinstance(last_comp, int):
        target = target[last_comp]
    
    if isinstance(target, list):
        target.append(parse_json(value))
    
    return data


def json_merge(*json_objects: Any) -> Dict:
    """
    Merge multiple JSON objects.
    
    Later objects overwrite earlier ones.
    
    Args:
        *json_objects: JSON objects to merge
    
    Returns:
        Merged JSON object
    """
    result = {}
    
    for obj in json_objects:
        try:
            parsed = parse_json(obj)
            if isinstance(parsed, dict):
                result.update(parsed)
        except JSONError:
            continue
    
    return result


def json_pretty_print(json_data: Any) -> str:
    """
    Format JSON with indentation.
    
    Args:
        json_data: JSON data
    
    Returns:
        Formatted JSON string
    """
    try:
        data = parse_json(json_data)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except JSONError:
        return str(json_data)


def _parse_json_path(path: str) -> List[Union[str, int]]:
    """
    Parse JSON path into components.
    
    Args:
        path: JSON path like "$.store.book[0].title"
    
    Returns:
        List of path components (strings or integers)
    """
    if not path.startswith('$'):
        path = '$' + path
    
    components = []
    current = ''
    i = 1  # Skip '$'
    
    while i < len(path):
        char = path[i]
        
        if char == '.':
            if current:
                components.append(current)
                current = ''
            i += 1
        elif char == '[':
            if current:
                components.append(current)
                current = ''
            # Parse array index
            i += 1
            idx_str = ''
            while i < len(path) and path[i] != ']':
                idx_str += path[i]
                i += 1
            if idx_str == '*':
                components.append('*')
            else:
                try:
                    components.append(int(idx_str))
                except ValueError:
                    components.append(idx_str)
            i += 1  # Skip ']'
        else:
            current += char
            i += 1
    
    if current:
        components.append(current)
    
    return components


def _is_json_path(column: str) -> bool:
    """
    Check if column string contains JSON path operator.
    
    Args:
        column: Column specification
    
    Returns:
        True if it's a JSON path expression
    """
    return '->' in column


def extract_json_path(column: str) -> tuple:
    """
    Extract column name and JSON path from expression.
    
    Args:
        column: Like "data->$.name" or "data->>$.name"
    
    Returns:
        (column_name, path, as_text) where as_text is True for ->>
    """
    # Match ->> (returns text) or -> (returns JSON)
    match = re.match(r'^(\w+)->(>?)(.+)$', column)
    if match:
        col_name = match.group(1)
        as_text = match.group(2) == '>'
        path = match.group(3)
        return col_name, path, as_text
    
    return column, None, False


# SQL-style JSON functions
def json_object(*args) -> Dict:
    """
    Create JSON object from key-value pairs.
    
    Args:
        *args: Alternating keys and values
    
    Returns:
        JSON object
    """
    result = {}
    for i in range(0, len(args), 2):
        if i + 1 < len(args):
            key = args[i]
            value = args[i + 1]
            result[key] = parse_json(value) if isinstance(value, str) else value
    return result


def json_array(*args) -> List:
    """
    Create JSON array from values.
    
    Args:
        *args: Values for array
    
    Returns:
        JSON array
    """
    return [parse_json(arg) if isinstance(arg, str) else arg for arg in args]


def json_type(json_data: Any, path: Optional[str] = None) -> Optional[str]:
    """
    Get type of JSON value.
    
    Args:
        json_data: JSON data
        path: Optional path
    
    Returns:
        Type name: 'object', 'array', 'string', 'number', 'boolean', 'null'
    """
    try:
        data = parse_json(json_data)
    except JSONError:
        return None
    
    if path:
        data = json_extract(data, path)
    
    if data is None:
        return 'null'
    elif isinstance(data, dict):
        return 'object'
    elif isinstance(data, list):
        return 'array'
    elif isinstance(data, str):
        return 'string'
    elif isinstance(data, bool):
        return 'boolean'
    elif isinstance(data, (int, float)):
        return 'number'
    
    return None


def json_valid(value: Any) -> bool:
    """
    Check if value is valid JSON.
    
    Args:
        value: Value to check
    
    Returns:
        True if valid JSON
    """
    return validate_json(value)


# Example usage
if __name__ == '__main__':
    # Test validation
    print("Validation tests:")
    print(f"  Valid JSON string: {validate_json('{\"a\": 1}')}")
    print(f"  Invalid JSON: {validate_json('not json')}")
    print(f"  Dict is valid: {validate_json({'a': 1})}")
    
    # Test extraction
    print("\nExtraction tests:")
    data = '{"user": {"name": "Alice", "age": 30}, "items": [1, 2, 3]}'
    print(f"  Extract $.user.name: {json_extract(data, '$.user.name')}")
    print(f"  Extract $.items[0]: {json_extract(data, '$.items[0]')}")
    print(f"  Extract text: {json_extract_text(data, '$.user.name')}")
    
    # Test contains
    print("\nContains tests:")
    print(f"  Contains 1: {json_contains(data, 1)}")
    print(f"  Contains 'Alice': {json_contains(data, 'Alice')}")
    
    # Test keys and length
    print("\nKeys and length tests:")
    print(f"  Keys: {json_keys(data, '$.user')}")
    print(f"  Array length: {json_array_length(data, '$.items')}")

# Validation Error Analysis and Fixes

## Issues Found

After analyzing the error logs from the test run on real data, I identified **two main validation issues** that were causing false positives:

### Issue 1: Asterisk-Suffixed Field Names (PRIMARY CAUSE)

**Problem:** 
- Schema field names include asterisks to indicate required fields (e.g., `"Account Name*"`, `"Device Name*"`, `"Name*"`, `"Last Name*"`)
- Raw source data has field names WITHOUT asterisks (e.g., `"Account Name"`, `"Device Name"`, `"Name"`, `"Last Name"`)
- The mapping logic in `_map_row()` couldn't find the data because it was looking for keys with asterisks in a dictionary that only had keys without asterisks
- Result: All required fields starting with these asterisk-suffixed names appeared as "Field is required" errors

**Evidence:**
From Accounts_errors.csv:
```
field: "Account Name*"
reason: "Field is required."
original_value: "" (empty)
raw_row: {"Account Name": "1 RIDGEWAY DR", ...}
```

From Devices_errors.csv:
```
field: "Device Name*"
reason: "Field is required."
original_value: "" (empty)
raw_row: {"Device Name": "Symmetry IGD Elevator", ...}
```

From Contacts_errors.csv:
```
field: "Last Name*"
reason: "Field is required."
original_value: "" (empty)
raw_row: {"Last Name": "Patel", ...}
```

**Note:** The asterisks have nothing to do with values starting with numbers - the data values like "1 RIDGEWAY DR" were present but not being mapped due to the field name mismatch.

### Issue 2: Incorrect Field Type in Schema

**Problem:**
- In `schemas/fieldboss/accounts.json`, the field `"Account Email"` was defined with type `"boolean"` instead of `"string"`
- When actual email addresses like "ulatowski1@verizon.net" were provided, validation failed with "Expected value of type 'boolean'"
- Email fields should be string type with optional "format": "email" validation

**Evidence:**
From Accounts_errors.csv:
```
field: "Account Email"
reason: "Expected value of type 'boolean'."
original_value: "ulatowski1@verizon.net"
```

## Fixes Implemented

### Fix 1: Update `_map_row()` Function (pipeline.py)

Modified the field lookup logic to handle asterisk-suffixed field names:

```python
for target_field in output_columns:
    if is_blank(standardized.get(target_field)) and target_field in raw_row:
        standardized[target_field] = raw_row.get(target_field)

    # Try without trailing asterisk if field name ends with '*' (indicates required field)
    if is_blank(standardized.get(target_field)) and target_field.endswith('*'):
        field_without_asterisk = target_field[:-1]
        if field_without_asterisk in raw_row:
            standardized[target_field] = raw_row.get(field_without_asterisk)

    # ... rest of logic
```

**Impact:** 
- Fields ending with `*` now correctly map to source data without asterisks
- Affects: `Account Name*`, `Device Name*`, `Name*`, `Last Name*`, and similar fields across all entities
- Resolves errors for ALL required fields that were showing as missing

### Fix 2: Correct Account Email Field Type (schemas/fieldboss/accounts.json)

Changed:
```json
"Account Email": { "type": "boolean", "required": false }
```

To:
```json
"Account Email": { "type": "string", "required": false, "format": "email" }
```

**Impact:**
- Email addresses can now be properly validated as strings with email format
- Resolves "Expected value of type 'boolean'" errors for Account Email field

## Root Cause Analysis

The asterisk in field names appears to be a design pattern to visually indicate required fields in configuration files. However, this created a mismatch:

1. **Schema Definition**: Uses asterisk-suffixed names (e.g., `"Account Name*"`)
2. **Mapping Definition**: Also uses asterisk-suffixed names in transformations
3. **Source Data**: Has clean field names without asterisks (e.g., `"Account Name"`)
4. **Mapping Logic**: Wasn't handling this translation

The fix allows the system to gracefully handle this pattern by attempting both with and without the asterisk suffix.

## Validation of Fixes

The issues were NOT caused by:
- ❌ Values starting with numbers being rejected (these were properly stored in raw_row)
- ❌ Type validation on numeric values (numbers like 34359, 1 were correctly handled)
- ❌ The `is_blank()` function rejecting legitimate data (it correctly identifies blank vs non-blank)

The issues WERE caused by:
- ✅ Field name mismatch (asterisk suffix) preventing data from being found during mapping
- ✅ Wrong type definition in schema for Account Email field

## Files Modified

1. `src/data_standardizer/pipeline.py` - Updated `_map_row()` function
2. `schemas/fieldboss/accounts.json` - Fixed Account Email field type

## Expected Impact After Fixes

Running the validation again should result in:
- Elimination of false "Field is required" errors for asterisk-suffixed required fields
- Proper validation of Account Email addresses as email format strings
- Improved accuracy in validation reporting - only real errors will be flagged

## Testing Recommendations

1. Re-run the standardization process on the same Core Records data
2. Compare error counts before and after
3. Verify that rows with data in fields like "Account Name", "Device Name", "Last Name" are now accepted
4. Verify email addresses in "Account Email" field are now properly validated

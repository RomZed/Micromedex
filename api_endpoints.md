# Micromedex CKO JSON API — Endpoint Reference

Source: *Merative ISI CKO Server Platform JSON Getting Started Guide*

---

## Single Endpoint Architecture

ALL CKO services use **one HTTP endpoint**:

```
POST https://www.micromedexsolutions.com/ckoapp/librarian/PFActionId/ckoapp.JsonRequest
Content-Type: application/json
Authorization: Basic <base64(username:password)>
```

Authentication uses **HTTP Basic Auth** (username + password, base64-encoded).
The `RequestType` field in the JSON body routes to the correct CKO service.
CKO returns **HTTP 200 for all responses** — check `IS_SUCCESS` in the body.

---

## 1. LookUp Service (`LUSRequest`)

Resolves drug names to codes before using other services.

### Request
```json
{
  "RequestType": "LUSRequest",
  "Request": {
    "LookUpType": "GNGCRRT",
    "SearchParameterList": {
      "OPERATOR": "OR",
      "SearchParameters": [
        { "NAME": "key", "VALUE": "warfarin" }
      ]
    }
  }
}
```

### Useful LookUpTypes for drug search
| LookUpType       | Description                               | Search Qualifier | Returns                      |
|------------------|-------------------------------------------|------------------|------------------------------|
| `GNGCRRT`        | Generic name → GCR code + route           | `key`            | GCRName, GCRCode, RouteName  |
| `PRDGCRRT`       | Product (brand) name → GCR + route        | `key`            | ProductName, GCRName, GCRCode|
| `GENERIC_NAME`   | Full generic name lookup by name or GFC   | `generic_name`, `gfc` | generic_name, gfc, route, form, strength |
| `NDCGFC`         | NDC → GFC cross-reference                 | `ndc`            | ndc, gfc                     |
| `ALLERGY`        | Allergy name → MDX_ALG code               | `allergy_name`   | allergy_name, mdxalg         |
| `PSDSINGLEDOSEKEY` | PSD dose key by GCR ID                  | `gcr_id`         | Full PSD key fields          |
| `DRUGCODESLOOKUP`| Cross-reference drug codes (ATC↔GFC etc.) | `source_code_type`, `source_code_value` | target_code_type, target_code_value |

### Response
```json
{
  "ResponseType": "LUSResult",
  "Response": {
    "LookUpRecordList": [
      { "LookUpRecord": "104045|WARFARIN SODIUM|ORAL" }
    ],
    "HEADER": "GCRCode|GCRName|RouteName",
    "SIZE": 1,
    "SUCCESS": "TRUE",
    "NUMBER_OF_FIELDS": 3
  }
}
```
Parse each `LookUpRecord` by splitting on `|`, then map positions using `HEADER`.

---

## 2. Status Service (`ServiceStatusRequest`)

Returns data-version status for all CKO services.

### Request
```json
{
  "RequestType": "ServiceStatusRequest",
  "Request": {}
}
```

### Response
```json
{
  "ResponseType": "ServiceStatusResult",
  "Response": {
    "DataSetList": {
      "DataSet": [
        {
          "TYPE": "DOSE1090_DATA",
          "ContentSetList": {
            "ContentSet": [
              { "TIME_STAMP": "201502111516", "NAME": "ckothids2", "VERSION": "196.00" }
            ],
            "SIZE": 1
          }
        }
      ],
      "SIZE": 9
    },
    "IS_SUCCESS": "TRUE"
  }
}
```

---

## 3. MAS — Validate Profile (`MASValidationRequest`)

Verify drugs, allergens, indications exist in MAS **before** screening.

### Request
```json
{
  "RequestType": "MASValidationRequest",
  "Request": {
    "CurrentDrugList": {
      "Drug": [{ "CODE": "00056-0172-70", "TYPE": "NDC", "ORDER_ID": "123-AA" }]
    },
    "NewDrugList": {
      "Drug": [{ "CODE": "104045", "TYPE": "GCR" }]
    },
    "AllergenList": {
      "Allergen": [{ "CODE": "7700090", "TYPE": "MDX_ALG" }]
    },
    "IndicationList": {
      "Indication": [{ "CODE": "011.30", "TYPE": "ICD_9" }]
    }
  }
}
```

Drug TYPE: `GCR`, `GFC`, `NDC` | Allergen TYPE: `NDC`, `MDX_ALG` | Indication TYPE: `ICD_9`, `ICD_10`, `MDX_CONCEPT`

### Response
```json
{
  "ResponseType": "MasValidateResult",
  "Response": {
    "WarningList": {
      "Warning": [
        {
          "ID": 1009048,
          "WarningText": "Drug: 999999 Not in the Micromedex Screening Database: 999999",
          "ItemList": { "TYPE": "INTERACTING_DRUG", "SIZE": 1,
            "Item": [{ "ID": "999999", "TYPE": "GFC" }]
          }
        }
      ],
      "SIZE": 1
    },
    "WARNING_TOTAL": 1,
    "IS_SUCCESS": "TRUE"
  }
}
```

---

## 4. MAS — Drug Screening (`MasRequest`)

Core drug interaction screening with full patient context.

### Request
```json
{
  "RequestType": "MasRequest",
  "Request": {
    "CLASS": "PROFESSIONAL",
    "Patient": {
      "GENDER": "FEMALE",
      "BD_YEAR": "1955",
      "BD_MONTH": "2",
      "BD_DAY": "23",
      "PREGNANT": "FALSE",
      "LACTATING": "TRUE",
      "SMOKER": "TRUE"
    },
    "CurrentDrugList": {
      "Drug": [{ "CODE": "00056-0172-70", "TYPE": "NDC", "ORDER_ID": "123-AA" }]
    },
    "NewDrugList": {
      "Drug": [{ "CODE": "104045", "TYPE": "GCR" }]
    },
    "AllergenList": {
      "Allergen": [{ "CODE": "7700090", "TYPE": "MDX_ALG" }]
    },
    "IndicationList": {
      "Indication": [{ "CODE": "011.30", "TYPE": "ICD_9" }]
    },
    "Filter": {
      "SEVERITY": "MODERATE",
      "DOCUMENTATION_RATING": "UNLIKELY",
      "TypeFilter": [
        { "NAME": "DRUG" },
        { "NAME": "DISEASE" },
        { "NAME": "ALLERGY" },
        { "NAME": "TC_DUPLICATION" },
        { "NAME": "INGREDIENT_DUPLICATION" }
      ]
    }
  }
}
```

**CLASS**: `PROFESSIONAL` | `CONSUMER`  
**SEVERITY filter** (minimum): `CONTRAINDICATED`, `MAJOR`, `MODERATE`, `MINOR`  
**TypeFilter NAMEs**: `DRUG`, `FOOD`, `ETHANOL`, `LAB`, `TOBACCO`, `ALLERGY`, `TC_DUPLICATION`, `ANTAGONISM`, `INGREDIENT_DUPLICATION`, `DISEASE`, `PREGNANCY`, `LACTATION`, `PRECAUTION`

### Response
```json
{
  "ResponseType": "MasResult",
  "Response": {
    "Summary": {
      "InteractionTypeSummaryList": {
        "InteractionTypeSummary": [
          { "TOTAL": 1, "TYPE": "DISEASE", "MAX_SEVERITY": "MODERATE" }
        ],
        "SIZE": 1
      },
      "INTERACTION_TOTAL": 1,
      "WARNING_TOTAL": 1
    },
    "WarningList": {
      "Warning": [
        {
          "ID": 6000003,
          "Type": "DISEASE",
          "SEVERITY": "MODERATE",
          "DOCUMENTATION_RATING": "UNKNOWN",
          "MONOGRAPH_ID": "0",
          "SOURCE": "M",
          "WarningText": "There may be a contraindication to the use of COUMADIN in patients with Tuberculosis.",
          "PrimaryWarningItemRoute": null,
          "SecondaryWarningItemRoute": null,
          "ItemList": [
            {
              "TYPE": "SECONDARY_ITEM", "SIZE": 4,
              "Item": [
                { "ID": "00056-0172-70", "TYPE": "NDC" },
                { "ID": "WARFARIN SODIUM", "TYPE": "GCR" }
              ]
            },
            {
              "TYPE": "INTERACTING_DRUG", "SIZE": 2,
              "Item": [
                { "ID": "011.30", "TYPE": "ICD_9" },
                { "ID": "Tuberculosis", "TYPE": "NAME" }
              ]
            }
          ]
        }
      ],
      "SIZE": 1
    },
    "IS_SUCCESS": "TRUE"
  }
}
```

---

## 5. MAS — Monograph (`DocumentRequest`)

Fetch full monograph for a warning's `MONOGRAPH_ID` from MasResult.

### Request
```json
{
  "RequestType": "DocumentRequest",
  "Request": {
    "DocumentList": {
      "Document": [
        { "ID": "6000003", "TYPE": "MONOGRAPH" }
      ]
    }
  }
}
```
TYPE must be `"MONOGRAPH"`.

---

## 6. DrugNotes (`DrugNotesRequest`)

Patient-friendly medication instructions (HTML text, multi-language).

### Request
```json
{
  "RequestType": "DrugNotesRequest",
  "Request": {
    "LANGUAGE": "English",
    "NewDrugList": {
      "Drug": [{ "CODE": "123456", "TYPE": "GFC" }]
    }
  }
}
```
TYPE: `GFC` or `NDC`. LANGUAGE: English, Spanish, French-Canadian, Portuguese-Brazilian, German, Italian, Japanese, Korean, Arabic, Russian, Turkish, Polish, Chinese-Simplified, Chinese-Traditional, Vietnamese.

---

## 7. Warning Labels (`WarningLabelsRequest`)

Pharmacy-style auxiliary warning label graphics/text.

### Request
```json
{
  "RequestType": "WarningLabelsRequest",
  "Request": {
    "NewDrugList": {
      "Drug": [{ "CODE": "12345-6789-10", "TYPE": "NDC" }]
    }
  }
}
```

---

## 8. DrugPoints (`DrugPointsRequest`)

Concise clinical drug monograph summaries.

### Request
```json
{
  "RequestType": "DrugPointsRequest",
  "Request": {
    "NewDrugList": {
      "Drug": [{ "CODE": "12345-6789-10", "TYPE": "NDC" }]
    }
  }
}
```
TYPE: `NDC` or `GFC`.

---

## 9. IV Screening (`IVScreeningRequest`)

IV drug compatibility screening.

### Request
```json
{
  "RequestType": "IVScreeningRequest",
  "Request": {
    "NewDrugList": {
      "Drug": [{ "CODE": "12345-6789-10", "TYPE": "NDC" }]
    }
  }
}
```

---

## 10. Patient Specific Dosing V2 (`PSDRequest`)

Patient-adjusted dosing recommendations.

### Workflow
1. Use LookUp `PSDSINGLEDOSEKEY` with `gcr_id` to get dose key fields
2. Build `RxDoseKey` from those fields
3. Submit `PSDRequest`

---

## 11. Validate (`ValidationRequest`)

Pre-validates drugs for specific CKO services.

### Request
```json
{
  "RequestType": "ValidationRequest",
  "Request": {
    "DRUGPOINTS": "YES",
    "PSD": "YES",
    "IVSCREENING": "YES",
    "WARNINGLABELS": "YES",
    "IMAGESIMPRINTS": "YES",
    "DRUGNOTES": "NO",
    "NewDrugList": {
      "Drug": [{ "CODE": "00029-3211-13", "TYPE": "NDC" }]
    }
  }
}
```

---

## Error Handling

CKO returns **HTTP 200 for all responses**. Check `IS_SUCCESS` in the body:
- `"IS_SUCCESS": "TRUE"` — success
- `"IS_SUCCESS": "FALSE"` — failure; inspect `ErrorList`

Warnings with `"Type": "VALIDATE"` in MasResult mean the drug was not found in the database.

---

## Drug Code Types

| Type  | Format               | Example          |
|-------|----------------------|------------------|
| GCR   | Numeric              | `104045`         |
| GFC   | 6-digit numeric      | `123456`         |
| NDC   | 5-4-2 dash-separated | `00056-0172-70`  |
| NAME  | Text (returned only) | `WARFARIN SODIUM`|

class HealthExtraction {
  missing_fields string[]
}

class BalanceExtraction {
  exchange string?
  account string?
  token string?
  market string?
  missing_fields string[]
}

class TransferExtraction {
  mode string?
  token string?
  from_exchange string?
  amount float?
  sub_account_name string?
  to_exchange string?
  missing_fields string[]
}

class MonitorExtraction {
  update_time int?
  missing_fields string[]
}

class VolumeFillsExtraction {
  symbol string?
  date string?
  missing_fields string[]
}

class StackerStatusExtraction {
  symbol string?
  date string?
  missing_fields string[]
}

function ExtractHealthRequest(user_question: string) -> HealthExtraction {
  client OpsExtractor
  prompt #"
    Extract parameters for GET /health from the user request.
    This endpoint has no payload fields.

    User request:
    {{ user_question }}

    Return missing_fields as an empty list unless the message is not a health
    check request.

    {{ ctx.output_format }}
  "#
}

function ExtractBalanceRequest(user_question: string) -> BalanceExtraction {
  client OpsExtractor
  prompt #"
    Extract parameters for POST /get-balance from the user request.

    Rules:
    - exchange is required.
    - account is optional; use main if not provided.
    - token is optional; use USDT if not provided.
    - token must be uppercase.
    - market is required only for futures exchanges: kcf, binf, fintradef.
    - supported exchanges are kc, kcf, kucoin, kucoinf, bybit, byb, okx,
      gate, gateio, binance, bin, binf, binancef, bitget, mexc, fintrade,
      fintradef.
    - Put any required but missing fields in missing_fields.

    User request:
    {{ user_question }}

    {{ ctx.output_format }}
  "#
}

function ExtractTransferRequest(user_question: string) -> TransferExtraction {
  client OpsExtractor
  prompt #"
    Extract parameters for POST /run-transfer from the user request.

    Supported modes:
    - sub_to_main: sub-account to main. Requires sub_account_name for kc.
    - main_to_sub: main to sub-account. Requires sub_account_name for kc.
    - withdraw: withdraw to another exchange. Requires to_exchange.
    - future_to_spot: futures to spot. Requires sub_account_name for kcf.
    - spot_to_future: spot to futures. Requires sub_account_name for kcf.
    - future_to_main: futures to main. Requires sub_account_name and kcf only.
    - main_to_future: main to futures. Requires sub_account_name and kcf only.
    - trading_to_funding: OKX only.

    Required fields:
    - mode
    - token, uppercase
    - from_exchange
    - amount, positive number
    - sub_account_name when required by mode/exchange
    - to_exchange for withdraw

    Interpret phrases:
    - "sub to main" means mode sub_to_main.
    - "main to sub" means mode main_to_sub.
    - "future to spot" means mode future_to_spot.
    - "spot to future" means mode spot_to_future.
    - "future to main" means mode future_to_main.
    - "main to future" means mode main_to_future.
    - "trading to funding" means mode trading_to_funding.

    Put any required but missing fields in missing_fields.

    User request:
    {{ user_question }}

    {{ ctx.output_format }}
  "#
}

function ExtractMonitorRequest(user_question: string) -> MonitorExtraction {
  client OpsExtractor
  prompt #"
    Extract parameters for POST /run-monitor from the user request.

    Rules:
    - update_time is optional.
    - If update_time is not provided, leave it null; Python will default to 10.
    - Put required missing fields in missing_fields. This endpoint has no
      required payload fields.

    User request:
    {{ user_question }}

    {{ ctx.output_format }}
  "#
}

function ExtractVolumeFillsRequest(user_question: string) -> VolumeFillsExtraction {
  client OpsExtractor
  prompt #"
    Extract parameters for POST /get_volume_strategy_fills from the user request.

    Rules:
    - symbol is required.
    - symbol may be provided as a full pair like KAIO-USDT or just the base
      asset like KAIO.
    - Keep symbol as written by the user except normalize obvious separators
      mentally; Python will normalize final formatting.
    - date is optional and should be YYYYMMDD if present.
    - Put any required but missing fields in missing_fields.

    User request:
    {{ user_question }}

    {{ ctx.output_format }}
  "#
}

function ExtractStackerStatusRequest(user_question: string) -> StackerStatusExtraction {
  client OpsExtractor
  prompt #"
    Extract parameters for POST /get_stacker_accepted_orders from the user request.

    Rules:
    - symbol is required.
    - symbol may be provided as a full pair like KAIO-USDT or just the base
      asset like KAIO.
    - Keep symbol as written by the user except normalize obvious separators
      mentally; Python will normalize final formatting.
    - date is optional and should be YYYYMMDD if present.
    - Put any required but missing fields in missing_fields.

    User request:
    {{ user_question }}

    {{ ctx.output_format }}
  "#
}

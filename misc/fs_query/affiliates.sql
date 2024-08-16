-- Query by @banbannard
with base as (select tx_id,
                     to_date(block_timestamp) as date, affiliate_address, affiliate_fee_basis_points, split(from_asset, '-') [0] as from_assets, case
    when from_assets ilike '%/%' then split(from_assets, '/') [1]
    else split(from_assets, '.') [1]
end
as from_asset_names,
    split(to_asset, '-') [0] as to_assets,
    case
      when to_assets ilike '%/%' then split(to_assets, '/') [1]
      else split(to_assets, '.') [1]
end
as to_asset_names,
    concat(from_asset_names, ' -> ', to_asset_names) as assets,
    case
      when assets ilike '%RUNE' then 2
      else 1
end
as numbering,
    sum(from_amount_usd) as swap_volume
  from
    thorchain.defi.fact_swaps
  WHERE
    BLOCK_TIMESTAMP >= GETDATE() - Interval '14 day'
  group by
    tx_id,
    date,
    affiliate_address,
    affiliate_fee_basis_points,
    from_asset,
    to_asset
),
base2 as (
  select
    date,
    tx_id,
    affiliate_address,
    affiliate_fee_basis_points,
    array_agg(distinct assets) within group (
      order by
        assets asc
    ) as swap_direction,
    --merging 2 sep path to 1
    sum(swap_volume) as swap_volume
  from
    base
  group by
    1,
    2,
    3,
    4
),
base3 as (
  select
    date,
    tx_id,
    affiliate_address,
    affiliate_fee_basis_points,
    swap_direction [0] as path1,
    swap_direction [1] as path2,
    case
      when path2 is null then path1
      when substr(path1, 1, 4) = 'RUNE' then path2
      else path1
    end as swap_path1,
    case
      when path2 is null then null
      when substr(path1, 1, 4) = 'RUNE' then path1
      else path2
    end as swap_path2,
    case
      when swap_path2 is null then swap_path1
      else concat(swap_path1, ' -> ', swap_path2)
    end as swap_paths,
    case
      when swap_paths ilike '%RUNE -> RUNE%' then replace(swap_paths :: string, 'RUNE -> RUNE', 'RUNE')
      else swap_paths
    end as swap_path,
    sum(swap_volume) as swap_vol,
    case
      when split(swap_path, '->') [2] is null then swap_vol
      else swap_vol / 2
    end as swap_volume,
    count(distinct(tx_id)) as swap_count
  from
    base2
  group by
    1,
    2,
    3,
    4,
    5,
    6
  order by
    swap_volume desc
),
base4 as (
  select
    date as day,
    case
      when affiliate_address in (
        't',
        'T',
        'tl',
        'thor160yye65pf9rzwrgqmtgav69n6zlsyfpgm9a7xk'
      ) then 'THORSwap'
      when affiliate_address in (
        'wr',
        'thor1a427q3v96psuj4fnughdw8glt5r7j38lj7rkp8'
      ) then 'THORWallet'
      when affiliate_address = 'cb' then 'Team CoinBot'
      when affiliate_address = 'tl' then 'TS Ledger'
      when affiliate_address = 'dx' then 'Asgardex'
      when affiliate_address = 'ss' then 'ShapeShift'
      when affiliate_address = 'xdf' then 'xDEFI'
      when affiliate_address = 'rg' then 'Rango'
      when affiliate_address = 'ej' then 'Edge Wallet'
      when affiliate_address = 'lifi' then 'LiFi'
      when affiliate_address = 'oky' then 'OneKey Wallet'
      when affiliate_address = 'ds' then 'DefiSpot'
      when affiliate_address in ('ti', 'td', 'te', 'te-ios', 'tr') then 'TrustWallet'
      when affiliate_address = 'sy' then 'Symbiosis'
      when affiliate_address = 'vi' then 'Vultisig'
      when affiliate_address = 'cakewallet' then 'Cake Wallet'
      when affiliate_address = 'lends' then 'Lends'
      else affiliate_address
    end as label,
    sum(swap_volume) as swap_volume2,
    ifnull(affiliate_fee_basis_points, 0) as aff_bp,
    ifnull(
      swap_volume2 * affiliate_fee_basis_points / 10000,
      0
    ) as aff_fee
  from
    base3
  where
    affiliate_address is not null
  group by
    1,
    2,
    affiliate_fee_basis_points
)
select
    day, label, sum (aff_fee) as fee_usd, SUM (fee_usd) OVER(
    PARTITION BY label
    ORDER BY
    day ASC
    ) AS cumulative_fee_usd, SUM (fee_usd) OVER(
    ORDER BY
    day ASC
    ) AS total_cumulative_fee_usd
from
    base4
where
    aff_fee
    > 0 -- and day > '2022-04-24'
group by
    day,
    label
order by
    day desc
BLOCK_CONSTANTS = {
    name.upper() for name in [
        'BlocksPerYear', 'FundMigrationInterval', 'ChurnInterval', 'ChurnRetryInterval',
        'SigningTransactionPeriod', 'DoubleSignMaxAge', 'LiquidityLockUpBlocks',
        'ObservationDelayFlexibility', 'YggFundRetry', 'JailTimeKeygen', 'JailTimeKeysign',
        'NodePauseChainBlocks', 'FullImpLossProtectionBlocks', 'TxOutDelayMax', 'MaxTxOutOffset',
    ]
}

RUNE_CONSTANTS = {
    name.upper() for name in [
        'OutboundTransactionFee',
        'NativeTransactionFee',
        'StagedPoolCost',
        'MinRunePoolDepth',
        'MinimumBondInRune',
        'MinTxOutVolumeThreshold',
        'TxOutDelayRate',
        'TNSFeePerBlock',
        'TNSRegisterFee',
        'MAXIMUMLIQUIDITYRUNE',
        'MAXLIQUIDITYRUNE',
        'PoolDepthForYggFundingMin',
    ]
}

BOOL_CONSTANTS = {
    "HALTBCHCHAIN",
    "HALTBCHTRADING",
    "HALTBNBCHAIN",
    "HALTBNBTRADING",
    "HALTBTCCHAIN",
    "HALTBTCTRADING",
    "HALTETHCHAIN",
    "HALTETHTRADING",
    "HALTLTCCHAIN",
    "HALTLTCTRADING",
    "HALTTHORCHAIN",
    'HALTDOGECHAIN',
    'HALTDOGETRADING',
    'HALTTERRACHAIN',
    'HALTTERRATRADING',

    'HALTHAVENCHAIN',

    'HALTCHURNING',
    "HALTTRADING",
    "MINTSYNTHS",
    "PAUSELP",
    "PAUSELPBCH",
    "PAUSELPBNB",
    "PAUSELPBTC",
    "PAUSELPETH",
    "PAUSELPLTC",
    "PAUSELPDOGE",
    'PAUSELPTERRA',
    "STOPFUNDYGGDRASIL",
    "STOPSOLVENCYCHECK",
    "THORNAME",
    "THORNAMES",
    'STOPSOLVENCYCHECKETH',
    'STOPSOLVENCYCHECKBNB',
    'STOPSOLVENCYCHECKLTC',
    'STOPSOLVENCYCHECKBTC',
    'STOPSOLVENCYCHECKBCH',
    'STOPSOLVENCYCHECKDOGE',
    'STOPSOLVENCYCHECKTERRA',
    'STRICTBONDLIQUIDITYRATIO',
}

TRANSLATE_MIMIRS = {
    'PAUSELPLTC': 'Pause LP LTC',
    'PAUSELPETH': 'Pause LP ETH',
    'PAUSELPBCH': 'Pause LP BCH',
    'PAUSELPBNB': 'Pause LP BNB',
    'PAUSELPBTC': 'Pause LP BTC',
    'PAUSELPDOGE': 'Pause LP Doge',
    'PAUSELPTERRA': 'Pause LP Terra',
    'PAUSELP': 'Pause all LP',
    'STOPFUNDYGGDRASIL': 'Stop Fund Yggdrasil',
    'STOPSOLVENCYCHECK': 'Stop Solvency Check',
    'NUMBEROFNEWNODESPERCHURN': 'Number of New Nodes per Churn',
    'MINTSYNTHS': 'Mint Synths',

    'HALTBCHCHAIN': 'Halt BCH Chain',
    'HALTBCHTRADING': 'Halt BCH Trading',
    'HALTSIGNINGBCH': 'Halt BCH Signing',
    'SOLVENCYHALTBCHCHAIN': 'Solvency Halt BCH Chain',

    'HALTBNBCHAIN': 'Halt BNB Chain',
    'HALTBNBTRADING': 'Halt BNB Trading',
    'HALTSIGNINGBNB': 'Halt BNB Signing',
    'SOLVENCYHALTBNBCHAIN': 'Solvency Halt BNB Chain',

    'HALTBTCCHAIN': 'Halt BTC Chain',
    'HALTBTCTRADING': 'Halt BTC Trading',
    'HALTSIGNINGBTC': 'Halt BTC Signing',
    'SOLVENCYHALTBTCCHAIN': 'Solvency Halt BTC Chain',

    'HALTETHCHAIN': 'Halt ETH Chain',
    'HALTETHTRADING': 'Halt ETH Trading',
    'HALTSIGNINGETH': 'Halt ETH Signing',
    'SOLVENCYHALTETHCHAIN': 'Solvency Halt ETH Chain',

    'HALTLTCCHAIN': 'Halt LTC Chain',
    'HALTLTCTRADING': 'Halt LTC Trading',
    'HALTSIGNINGLTC': 'Halt LTC Signing',
    'SOLVENCYHALTLTCCHAIN': 'Solvency Halt LTC Chain',

    'HALTDOGECHAIN': 'Halt DOGE Chain',
    'HALTDOGETRADING': 'Halt DOGE Trading',
    'HALTSIGNINGDOGE': 'Halt DOGE Signing',
    'SOLVENCYHALTDOGECHAIN': 'Solvency Halt DOGE Chain',

    'HALTTERRACHAIN': 'Halt Terra Chain',
    'HALTTERRATRADING': 'Halt Terra Trading',
    'HALTSIGNINGTERRA': 'Halt Terra Signing',
    'SOLVENCYHALTTERRACHAIN': 'Solvency Halt Terra Chain',

    'HALTHAVENCHAIN': 'Halt Haven Chain',  # unconfirmed!

    'HALTGAIACHAIN': 'Halt Atom Chain',
    'HALTGAIATRADING': 'Halt Atom Trading',
    'HALTSIGNINGGAIA': 'Halt Atom Signing',
    'SOLVENCYHALTGAIACHAIN': 'Solvency Halt Atom Chain',

    'HALTTHORCHAIN': 'Halt ThorChain',
    'HALTTRADING': 'Halt All Trading',

    'MAXIMUMLIQUIDITYRUNE': 'Maximum Liquidity Rune',
    'MAXLIQUIDITYRUNE': 'Max Liquidity Rune',

    'MAXUTXOSTOSPEND': 'Max UTXO to Spend',

    'THORNAME': 'THOR Name',
    'THORNAMES': 'THOR Names',

    'STOPSOLVENCYCHECKETH': 'Stop Solvency check ETH',
    'STOPSOLVENCYCHECKBNB': 'Stop Solvency check BNB',
    'STOPSOLVENCYCHECKLTC': 'Stop Solvency check LTC',
    'STOPSOLVENCYCHECKBTC': 'Stop Solvency check BTC',
    'STOPSOLVENCYCHECKBCH': 'Stop Solvency check BCH',
    'STOPSOLVENCYCHECKDOGE': 'Stop Solvency check DOGE',
    'STOPSOLVENCYCHECKTERRA': 'Stop Solvency check Terra',
    'STRICTBONDLIQUIDITYRATIO': 'Strict Bond Liquidity Ratio',

    'POOLDEPTHFORYGGFUNDINGMIN': 'Pool Depth For Ygg Funding Min',

    'MAXSYNTHASSETDEPTH': 'Max Synth Asset Depth',
    'HALTCHURNING': 'Halt Churning',

    'MAXNODETOCHURNOUTFORLOWVERSION': 'Max Node To Churn Out For Low Version',

    'CLOUDPROVIDERLIMIT': 'Cloud Provider Limit',

    'DESIREDMAXVALIDATORSET': 'Desired Max Validator Set',
    'DESIREDVALIDATORSET': 'Desired Validator Set',

    'ENABLEUPDATEMEMOTERRA': 'Enable Update Memo Terra',
}

EXCLUDED_VOTE_KEYS = [
    'TEST',
    'SUPPORTTHORCHAINDOTNETWORK',
]


class MimirUnits:
    UNITS_RUNES = 'runes'
    UNITS_BLOCKS = 'blocks'
    UNITS_BOOL = 'bool'

    @staticmethod
    def get_mimir_units(name):
        if name in RUNE_CONSTANTS:
            return MimirUnits.UNITS_RUNES
        elif name in BLOCK_CONSTANTS:
            return MimirUnits.UNITS_BLOCKS
        elif name in BOOL_CONSTANTS:
            return MimirUnits.UNITS_BOOL
        else:
            return ''

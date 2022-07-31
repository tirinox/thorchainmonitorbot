MIMIR_KEY_KILL_SWITCH_START = 'KILLSWITCHSTART'
MIMIR_KEY_KILL_SWITCH_DURATION = 'KillSwitchDuration'.upper()

BLOCK_CONSTANTS = {
    name.upper() for name in [
        'BlocksPerYear', 'FundMigrationInterval', 'ChurnInterval', 'ChurnRetryInterval',
        'SigningTransactionPeriod', 'DoubleSignMaxAge', 'LiquidityLockUpBlocks',
        'ObservationDelayFlexibility', 'YggFundRetry', 'JailTimeKeygen', 'JailTimeKeysign',
        'NodePauseChainBlocks', 'FullImpLossProtectionBlocks', 'TxOutDelayMax', 'MaxTxOutOffset',
        MIMIR_KEY_KILL_SWITCH_DURATION, MIMIR_KEY_KILL_SWITCH_DURATION,
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

    'HALTSIGNINGBNB',
    'HALTSIGNINGBCH',
    'HALTSIGNINGBTC',
    'HALTSIGNINGETH',
    'HALTSIGNINGTERRA',
    'HALTSIGNINGLTC',
    'HALTSIGNINGGAIA',

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


DICT_WORDS = (
    'stop,max,bond,providers,slash,penalty,incentive,curve,emission,default,'
    'pool,status,pause,bond,kill,switch,'
    'bad,validator,rate,duration,fail,key,sign,points,'
    'minimum,permitted,asgard,size,pool,cycle,sym,withdrawal,'
    'minimum,for,yggdrasil,tx,out,offset,virtual,mult,'
    'synths,staged,cost,double,sign,age,per,swap,block,blocks,'
    'unbound,delay,outbound,transaction,fee,avax,enable,'
    'chain,observe,full,imp,loss,protection,min,burn,'
    'operator,ragnarok,terra,jail,time,available,pools,'
    'process,num,lp,mint,volume,threshold,support,thorchain,'
    'dot,network,observation,flexibility,attempts,liquidity,'
    'ygg,fund,retry,native,btf,migration,interval,remove,'
    'snx,text,low,tns,register,period,usd,global,old,depth,'
    'lack,penalty,chain,node,version,churn,to,provider,nodes,lock,'
    'up,synth,in,rune,limit,gap,solvency,of,gen,year,start,asym,swtich,start,'
    'on,halt,unbond,iteration,sale,reward,ratio,strict,maximum,churning,btc,bch,ltc,doge,terra,avax,atom,gaia,bnb,eth,'
    'thor,utxos,check,trading,thorname,thornames,asset,signing,set,haven,spend,funding,cloud,new,number,desired,'
    'update,memo'
).strip(' ,')

WORD_TRANSFORM = {
    'Thorchain': 'THORChain',
    'Thorname': 'THORName',
    'Thornames': 'THORNames',
    'Lp': 'LP',
    'Usd': 'USD',
    'Tns': 'TNS',
    'Btc': 'BTC',
    'Bch': 'BCH',
    'Ltc': 'LTC',
    'Bnb': 'BNB',
    'Eth': 'ETH',
    'Of': 'of',
    'On': 'on',
    'In': 'in',
    'From': 'from',
    'For': 'for',
}

DICT_WORDS_SORTED = list(sorted(map(str.upper, DICT_WORDS.split(',')), key=len, reverse=True))


def try_deducting_mimir_name(name: str, glue=' '):
    components = []
    name = name.upper()

    for word in DICT_WORDS_SORTED:
        word_len = len(word)
        while True:
            index = name.find(word)
            if index == -1:
                break
            else:
                components.append((index, word))
                name = name.replace(word, ' ' * word_len)

    components.sort()  # sort by index

    if not components:
        return name.upper() + '?'

    words = []
    position = 0
    for index, word in components:
        if index > position:
            missing_word = name[position:index]
            words.append(missing_word.upper())
        words.append(word.capitalize())
        position = index + len(word)

    if position < len(name):
        words.append(name[position:].upper())

    words = map(lambda w: WORD_TRANSFORM.get(w, w), words)

    return glue.join(words)

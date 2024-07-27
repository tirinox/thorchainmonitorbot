from services.lib.utils import invert_dict

MIMIR_KEY_KILL_SWITCH_START = 'KILLSWITCHSTART'
MIMIR_KEY_KILL_SWITCH_DURATION = 'KILLSWITCHDURATION'

MIMIR_KEY_MAX_SYNTH_PER_POOL_DEPTH = 'MAXSYNTHPERPOOLDEPTH'

# target synth per pool depth for POL (basis points)
MIMIR_KEY_POL_TARGET_SYNTH_PER_POOL_DEPTH = 'POLTARGETSYNTHPERPOOLDEPTH'
"""
if POLTargetSynthPerPoolDepth == 4500:
    POL will continue adding RUNE to a pool until the synth depth of that pool is 45%.
"""

# buffer around the POL synth utilization (basis points added to/subtracted from POLTargetSynthPerPoolDepth basis pts)
MIMIR_KEY_POL_BUFFER = "POLBUFFER"
"""
if POLBUFFER == 500:
    Synth utilization must be >5% from the target synth per pool depth in order to add liquidity / remove liquidity. 
    In this context, liquidity will be withdrawn below 40% synth utilization and deposited above 50% synth utilization.
"""

# Maximum amount of rune deposited into the pools
MIMIR_KEY_POL_MAX_NETWORK_DEPOSIT = "POLMAXNETWORKDEPOSIT"

# Maximum amount of rune to enter/exit a pool per iteration. This is in basis points of the pool rune depth
MIMIR_KEY_POL_MAX_POOL_MOVEMENT = "POLMAXPOOLMOVEMENT"
"""
if POLMaxPoolMovement == 1:
    POL will move the pool price at most 0.01% in one block
"""

MIMIR_KEY_POL_SYNTH_UTILIZATION = "POLSYNTHUTILIZATION"

BLOCK_CONSTANTS = {
    'BLOCKSPERYEAR', 'FUNDMIGRATIONINTERVAL', 'CHURNINTERVAL', 'CHURNRETRYINTERVAL',
    'SIGNINGTRANSACTIONPERIOD', 'DOUBLESIGNMAXAGE', 'LIQUIDITYLOCKUPBLOCKS',
    'OBSERVATIONDELAYFLEXIBILITY', 'YGGFUNDRETRY', 'JAILTIMEKEYGEN', 'JAILTIMEKEYSIGN',
    'NODEPAUSECHAINBLOCKS', 'FULLIMPLOSSPROTECTIONBLOCKS', 'TXOUTDELAYMAX', 'MAXTXOUTOFFSET',
    MIMIR_KEY_KILL_SWITCH_DURATION, MIMIR_KEY_KILL_SWITCH_DURATION,
}

RUNE_CONSTANTS = {
    'OUTBOUNDTRANSACTIONFEE',
    'NATIVETRANSACTIONFEE',
    'STAGEDPOOLCOST',
    'MINRUNEPOOLDEPTH',
    'MINIMUMBONDINRUNE',
    'MINTXOUTVOLUMETHRESHOLD',
    'TXOUTDELAYRATE',
    'TNSFEEPERBLOCK',
    'TNSREGISTERFEE',
    'MAXIMUMLIQUIDITYRUNE',
    'MAXLIQUIDITYRUNE',
    'POOLDEPTHFORYGGFUNDINGMIN',
    'POLMAXNETWORKDEPOSIT',
    'MAXRUNESUPPLY',
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

    'ALTGAIACHAIN',
    'ENABLEAVAXCHAIN',
    'ENABLEUPDATEMEMOTERRA',
    'HALTGAIACHAIN',
    'RAGNAROK-TERRA',
    'RAGNAROK-TERRA-LUNA',
    'RAGNAROK-TERRA-USD',
    'RAGNAROK-TERRA-UST',
    'REMOVESNXPOOL',

    "POL-ETH-ETH",
    "POL-BTC-BTC",
    "POL-BNB-BNB",

    "RUNEPOOLENABLED",
}

DOLLAR_CONSTANTS = {
    'MINIMUML1OUTBOUNDFEEUSD',
}

BASIS_POINTS_CONSTANTS = {
    'MAXSYNTHPERASSETDEPTH',
    'MAXSYNTHPERPOOLDEPTH',
    'CLOUDPROVIDERLIMIT',
    'POLMAXPOOLMOVEMENT',
    'POLTARGETSYNTHPERPOOLDEPTH',
    'POLBUFFER',
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

    "POL-ETH-ETH": "POL ETH.ETH",
    "POL-BTC-BTC": "POL BTC.BTC",
    "POL-BNB-BNB": "POL BNB-BNB",
    "POLBUFFER": "POL Buffer",
    "POLMAXNETWORKDEPOSIT": "POL Max Network Deposit",
    "POLMAXPOOLMOVEMENT": "POL Max Pool Movement",
    "POLSYNTHUTILIZATION": "POL Synth Utilization",  # unused?
    "POLTARGETSYNTHPERPOOLDEPTH": "POL Target Synth Per Pool Depth",
}

EXCLUDED_VOTE_KEYS = [
    'TEST',
    'SUPPORTTHORCHAINDOTNETWORK',
]

NEXT_CHAIN_VOTING_MAP = invert_dict({
    'DASH': 9,
    'HAVEN': 10,
    'ZCASH': 11,
    'MONERO': 12,
    'DECRED': 13,
    'OSMOSIS': 14,
    'MOONBEAM': 15,
    'BNB Chain (BSC)': 16,
    'POLYGON': 17,
    'CARDANO': 18,
    'JUNO': 19,
})

NEXT_CHAIN_KEY = 'NextChain'.upper()


class MimirUnits:
    UNITS_RUNES = 'runes'
    UNITS_BLOCKS = 'blocks'
    UNITS_BOOL = 'bool'
    UNITS_NEXT_CHAIN = 'next_chain'
    UNITS_USD = 'usd'
    UNITS_BASIS_POINTS = 'basis_points'

    @staticmethod
    def get_mimir_units(name):
        name = name.upper()
        if name in RUNE_CONSTANTS:
            return MimirUnits.UNITS_RUNES
        elif name in BLOCK_CONSTANTS:
            return MimirUnits.UNITS_BLOCKS
        elif name in BOOL_CONSTANTS:
            return MimirUnits.UNITS_BOOL
        elif name in DOLLAR_CONSTANTS:
            return MimirUnits.UNITS_USD
        elif name == NEXT_CHAIN_KEY:
            return MimirUnits.UNITS_NEXT_CHAIN
        elif name in BASIS_POINTS_CONSTANTS:
            return MimirUnits.UNITS_BASIS_POINTS
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
    'update,memo,next,saving,savings,savers,vaults,vault,bsc,ilp,deprecate,pol,buffer,deposit,movement,utilization,'
    'thor,anchor,multiple,basis,dofm,pending,vote,voting,in,or,and,the,yield,streaming,stream,tor,top,lending,'
    'supply,multiplier,ETH-USDC,surplus,target,swaps,order,book,books,AVAX-USDC,significant,digits,length,'
    'red,line,lune,fees,affiliate,cut,off,BNB-BUSD-BD1,ETH-USDT,loan,repayment,maturity,lever,slip,pts,'
    'UST,luna,wide,blame,keygen,assets,derived,round,rounds,prefer,Collateral,ready,'
    'protocol,system,rev,incr,dynamic,trade,accounts,disabled,operational,security,bps,conf,rune'
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
    'Snx': 'SNX',
    'Of': 'of',
    'On': 'on',
    'In': 'in',
    'From': 'from',
    'For': 'for',
    'Bsc': 'BSC',
    'Ilp': 'ILP',
    'Pol': 'POL',
    'Tor': 'TOR',
    'Dofm': 'Dynamic Outbound Fee Multiplier',
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

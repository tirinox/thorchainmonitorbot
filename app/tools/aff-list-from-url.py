import pandas as pd
import requests
from bs4 import BeautifulSoup

from api.midgard.name_service import AffiliateManager
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


def read_affiliates_from_web(url="https://tcecosystem.guide/thorchain/affiliate-codes.html"):
    html = requests.get(url).text

    soup = BeautifulSoup(html, "html.parser")

    # Find the table
    table = soup.find("table")

    # Extract rows
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)

    # Convert to DataFrame
    df = pd.DataFrame(rows[1:], columns=rows[0])
    return df


def main():
    df = read_affiliates_from_web()
    df_question = df[df["Code"] != "?"][df["Affiliate"] != "?"]
    print(df_question)

    # make Code -> Affiliate mapping
    external_aff_dict = dict(zip(df_question["Code"], df_question["Affiliate"]))

    external_codes = set(external_aff_dict.keys())

    LpAppFramework.solve_working_dir_mess()

    aff = AffiliateManager()
    print(aff.thorname_to_name)
    known_codes = set(aff.thorname_to_name.keys())
    print(f'Known code count: {len(known_codes)}, External code count: {len(external_codes)}')

    new_codes = external_codes - known_codes
    print(f'New code count: {len(new_codes)}')
    for name in new_codes:
        print(f'New affiliate name found: {name} -> {external_aff_dict[name]}')

    # Ask confirmation to add new names
    if new_codes:
        sep()
        confirm = input(f"Do you want to add {len(new_codes)} new affiliate codes to the system? (y/n): ")
        if confirm.lower() == 'y':
            for code in new_codes:
                aff.add(code, external_aff_dict[code])
            aff.save()
            print("New affiliate names added and saved.")
        else:
            print("No changes made.")

    sep()
    any_changes = False
    for code in external_aff_dict:
        if code in known_codes:
            existing_name = aff.thorname_to_name[code]
            external_name = external_aff_dict[code]
            if existing_name != external_name:
                print(f'Conflict for code {code}: existing name "{existing_name}" vs external name "{external_name}"')
                # update?

    if any_changes:
        aff.save()
        print("Changes saved.")


if __name__ == "__main__":
    main()

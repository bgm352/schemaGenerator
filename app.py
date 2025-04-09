import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urlparse
import time

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def get_webpage_content(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching the webpage: {e}")
        return None

def generate_drug_schema(drug_name, generic_name, drug_description, manufacturer, active_ingredient, 
                         drug_class, prescription_status, same_as_urls, medical_codes=None, related_conditions=None):
    schema = {
        "@context": "https://schema.org",
        "@type": "Drug",
        "name": drug_name,
        "genericName": generic_name,
        "description": drug_description,
        "manufacturer": {
            "@type": "Organization",
            "name": manufacturer
        },
        "activeIngredient": active_ingredient,
        "drugClass": drug_class,
        "prescriptionStatus": prescription_status,
        "sameAs": same_as_urls
    }
    
    # Add medical codes if provided
    if medical_codes and len(medical_codes) > 0:
        schema["code"] = []
        for code in medical_codes:
            if code["system"] and code["value"]:
                schema["code"].append({
                    "@type": "MedicalCode",
                    "codeSystem": code["system"],
                    "codeValue": code["value"]
                })
    
    # Add related conditions if provided
    if related_conditions and len(related_conditions) > 0:
        schema["indication"] = []
        for condition in related_conditions:
            if condition["name"]:
                condition_obj = {
                    "@type": "MedicalCondition",
                    "name": condition["name"]
                }
                if condition["code_system"] and condition["code_value"]:
                    condition_obj["code"] = {
                        "@type": "MedicalCode",
                        "codeSystem": condition["code_system"],
                        "codeValue": condition["code_value"]
                    }
                schema["indication"].append(condition_obj)
    
    return schema

def generate_clinical_trial_schema(trial_id, trial_name, trial_description, sponsor, 
                                  health_condition, drug_name, trial_status, trial_phase,
                                  related_publications=None):
    schema = {
        "@context": "https://schema.org",
        "@type": "MedicalTrial",
        "identifier": trial_id,
        "name": trial_name,
        "description": trial_description,
        "sponsor": {
            "@type": "Organization",
            "name": sponsor
        },
        "healthCondition": health_condition,
        "studySubject": {
            "@type": "Drug",
            "name": drug_name
        },
        "status": trial_status,
        "phase": trial_phase
    }
    
    # Add related publications if provided
    if related_publications and len(related_publications) > 0:
        schema["citation"] = []
        for pub in related_publications:
            if pub["url"] and pub["title"]:
                schema["citation"].append({
                    "@type": "ScholarlyArticle",
                    "url": pub["url"],
                    "headline": pub["title"]
                })
    
    return schema

def inject_schema_into_html(html_content, schema_json):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Create a new script tag for the schema
    script_tag = soup.new_tag('script')
    script_tag['type'] = 'application/ld+json'
    script_tag.string = json.dumps(schema_json, indent=2)
    
    # Add the script tag to the head
    if soup.head:
        soup.head.append(script_tag)
    else:
        # Create head if it doesn't exist
        head = soup.new_tag('head')
        head.append(script_tag)
        soup.html.insert(0, head)
    
    return str(soup)

def highlight_schema(html_content):
    # Highlight the schema.org markup in the HTML
    pattern = r'(<script type="application/ld\+json">)(.*?)(</script>)'
    
    def highlight_match(match):
        script_open = match.group(1)
        json_content = match.group(2)
        script_close = match.group(3)
        
        # Format the JSON for better readability
        try:
            formatted_json = json.dumps(json.loads(json_content), indent=2)
        except:
            formatted_json = json_content
            
        return f'{script_open}{formatted_json}{script_close}'
    
    highlighted_html = re.sub(pattern, highlight_match, html_content, flags=re.DOTALL)
    return highlighted_html

def find_similar_websites(drug_name, generic_name=None, drug_class=None):
    """Find similar authoritative websites for a given drug with specific categorization"""
    similar_sites = []
    
    search_term = generic_name if generic_name else drug_name
    
    # Organized by recommended categories from the criteria
    sources = {
        "Chemical & Pharmacological Databases": [
            {
                "name": "DrugBank",
                "base_url": "https://go.drugbank.com",
                "search_pattern": f"https://go.drugbank.com/drugs/DB*",
                "example_url": f"https://go.drugbank.com/drugs/DB00043",
                "site_type": "Drug Database",
                "priority": "High"
            },
            {
                "name": "PubChem",
                "base_url": "https://pubchem.ncbi.nlm.nih.gov",
                "search_pattern": f"https://pubchem.ncbi.nlm.nih.gov/compound/*",
                "example_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/24822794",
                "site_type": "Chemical Database",
                "priority": "High"
            },
            {
                "name": "ChEMBL",
                "base_url": "https://www.ebi.ac.uk/chembl",
                "search_pattern": f"https://www.ebi.ac.uk/chembl/compound_report_card/*",
                "example_url": f"https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL1201606/",
                "site_type": "Bioactivity Database",
                "priority": "Medium"
            }
        ],
        "Regulatory & Clinical Sources": [
            {
                "name": "FDA",
                "base_url": "https://www.fda.gov",
                "search_pattern": f"https://www.fda.gov/drugs/postmarket-drug-safety-information-patients-and-providers/*",
                "example_url": f"https://www.fda.gov/drugs/postmarket-drug-safety-information-patients-and-providers/{drug_name.lower()}-{generic_name.lower() if generic_name else ''}-information",
                "site_type": "Regulatory Information",
                "priority": "Very High"
            },
            {
                "name": "ClinicalTrials.gov",
                "base_url": "https://clinicaltrials.gov",
                "search_pattern": f"https://clinicaltrials.gov/study/*",
                "example_url": f"https://clinicaltrials.gov/search?term=NCT00377572",
                "site_type": "Clinical Trials",
                "priority": "High"
            },
            {
                "name": "DailyMed",
                "base_url": "https://dailymed.nlm.nih.gov",
                "search_pattern": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=*",
                "example_url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=a30a77e6-8c30-4aa2-bec2-77fb5e13dc66",
                "site_type": "Label Information",
                "priority": "High"
            }
        ],
        "Medical Knowledge Graphs": [
            {
                "name": "Wikidata",
                "base_url": "https://www.wikidata.org",
                "search_pattern": f"https://www.wikidata.org/wiki/*",
                "example_url": f"https://www.wikidata.org/wiki/Q204711",
                "site_type": "Knowledge Graph",
                "priority": "Medium"
            },
            {
                "name": "Wikipedia",
                "base_url": "https://en.wikipedia.org",
                "search_pattern": f"https://en.wikipedia.org/wiki/*",
                "example_url": f"https://en.wikipedia.org/wiki/{generic_name.lower() if generic_name else drug_name.lower()}",
                "site_type": "Encyclopedia",
                "priority": "Medium"
            }
        ],
        "Standardized Ontologies": [
            {
                "name": "MeSH",
                "base_url": "https://meshb.nlm.nih.gov",
                "search_pattern": f"https://meshb.nlm.nih.gov/record/ui?ui=*",
                "example_url": f"https://meshb.nlm.nih.gov/record/ui?ui=C079635",
                "site_type": "Medical Ontology",
                "priority": "High"
            },
            {
                "name": "WHO ATC",
                "base_url": "https://www.whocc.no",
                "search_pattern": f"https://www.whocc.no/atc_ddd_index/?code=*",
                "example_url": f"https://www.whocc.no/atc_ddd_index/?code=R03DX05",
                "site_type": "Classification System",
                "priority": "Medium"
            }
        ],
        "Research & Publications": [
            {
                "name": "PubMed",
                "base_url": "https://pubmed.ncbi.nlm.nih.gov",
                "search_pattern": f"https://pubmed.ncbi.nlm.nih.gov/*",
                "example_url": f"https://pubmed.ncbi.nlm.nih.gov/?term={search_term}+clinical+trial",
                "site_type": "Research Database",
                "priority": "High"
            }
        ]
    }
    
    # Add all site categories to the results
    for category, category_sources in sources.items():
        for source in category_sources:
            similar_sites.append({
                "name": source["name"],
                "url": source["example_url"],
                "type": source["site_type"],
                "category": category,
                "priority": source["priority"]
            })
    
    return similar_sites

st.set_page_config(page_title="Drug Schema Markup Generator", layout="wide")

st.title("Drug Schema Markup Generator")
st.markdown("""
This application helps you generate and inject Schema.org markup for drugs, 
sameAs relationships, and clinical trials into your web pages. This enhances 
correlation between your site and trusted third-party sources that AI systems prefer to cite.
""")

tab1, tab2, tab3, tab4 = st.tabs(["Webpage Analysis", "Generate Drug Schema", "Generate Clinical Trial Schema", "Find Similar Sites"])

with tab1:
    st.header("Analyze Existing Webpage")
    url = st.text_input("Enter the URL of the webpage to analyze")
    
    if url and st.button("Analyze Webpage", key="analyze_btn"):
        if is_valid_url(url):
            with st.spinner("Fetching and analyzing the webpage..."):
                html_content = get_webpage_content(url)
                if html_content:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Find all schema.org markup
                    schema_scripts = soup.find_all('script', type='application/ld+json')
                    
                    if schema_scripts:
                        st.success(f"Found {len(schema_scripts)} schema.org markup blocks on the page")
                        for i, script in enumerate(schema_scripts):
                            try:
                                schema_data = json.loads(script.string)
                                st.subheader(f"Schema #{i+1}")
                                st.json(schema_data)
                            except json.JSONDecodeError:
                                st.error(f"Schema #{i+1} contains invalid JSON")
                    else:
                        st.warning("No schema.org markup found on the page")
        else:
            st.error("Please enter a valid URL")

with tab2:
    st.header("Generate Drug Schema")
    
    drug_name = st.text_input("Drug Name (Brand Name)", key="drug_name", value="Xolair")
    generic_name = st.text_input("Generic Name", key="generic_name", value="omalizumab")
    drug_description = st.text_area("Drug Description", key="drug_desc", 
                                    value="Xolair (omalizumab) is a monoclonal antibody that inhibits immunoglobulin E (IgE) binding to high-affinity receptors on the surface of mast cells and basophils.")
    manufacturer = st.text_input("Manufacturer", key="manufacturer", value="Genentech")
    active_ingredient = st.text_input("Active Ingredient", key="active_ingredient", value="omalizumab")
    drug_class = st.text_input("Drug Class", key="drug_class", value="Monoclonal antibody")
    
    prescription_status = st.selectbox(
        "Prescription Status",
        ["PrescriptionOnly", "OTC", "Discontinued"],
        key="prescription_status"
    )
    
    st.subheader("Medical Codes")
    st.markdown("Add standardized medical codes for better identification")
    
    code_cols = st.columns(2)
    medical_codes = []
    
    with code_cols[0]:
        code_system1 = st.text_input("Code System", key="code_system1", value="RxNorm")
        code_value1 = st.text_input("Code Value", key="code_value1", value="1650893")
        if code_system1 and code_value1:
            medical_codes.append({"system": code_system1, "value": code_value1})
    
    with code_cols[1]:
        code_system2 = st.text_input("Code System (Optional)", key="code_system2", value="WHO ATC")
        code_value2 = st.text_input("Code Value (Optional)", key="code_value2", value="R03DX05")
        if code_system2 and code_value2:
            medical_codes.append({"system": code_system2, "value": code_value2})
    
    st.subheader("Related Medical Conditions")
    st.markdown("Add conditions this drug treats (improves AI understanding of drug purpose)")
    
    condition_cols = st.columns(2)
    related_conditions = []
    
    with condition_cols[0]:
        condition_name1 = st.text_input("Condition Name", key="condition_name1", value="Moderate to severe persistent asthma")
        condition_code_system1 = st.text_input("Code System", key="condition_code_system1", value="ICD-10")
        condition_code_value1 = st.text_input("Code Value", key="condition_code_value1", value="J45.4")
        if condition_name1:
            related_conditions.append({
                "name": condition_name1, 
                "code_system": condition_code_system1, 
                "code_value": condition_code_value1
            })
    
    with condition_cols[1]:
        condition_name2 = st.text_input("Condition Name (Optional)", key="condition_name2", value="Chronic idiopathic urticaria")
        condition_code_system2 = st.text_input("Code System (Optional)", key="condition_code_system2", value="ICD-10")
        condition_code_value2 = st.text_input("Code Value (Optional)", key="condition_code_value2", value="L50.1")
        if condition_name2:
            related_conditions.append({
                "name": condition_name2, 
                "code_system": condition_code_system2, 
                "code_value": condition_code_value2
            })
    
    st.subheader("SameAs URLs (Trusted Sources)")
    st.markdown("""
    Add URLs to authoritative sources about this drug. These help establish trust relationships
    with sources that AI systems are more likely to cite.
    """)
    
    # For Xolair example, add the recommended URLs based on the provided criteria
    same_as_urls = []
    
    st.markdown("##### Chemical & Pharmacological Databases")
    db_cols = st.columns(2)
    with db_cols[0]:
        drugbank_url = st.text_input("DrugBank URL", key="drugbank", value="https://drugbank.ca/drugs/DB00043")
        if drugbank_url and is_valid_url(drugbank_url):
            same_as_urls.append(drugbank_url)
    
    with db_cols[1]:
        pubchem_url = st.text_input("PubChem URL", key="pubchem", value="https://pubchem.ncbi.nlm.nih.gov/compound/24822794")
        if pubchem_url and is_valid_url(pubchem_url):
            same_as_urls.append(pubchem_url)
    
    st.markdown("##### Regulatory & Clinical Sources")
    reg_cols = st.columns(2)
    with reg_cols[0]:
        fda_url = st.text_input("FDA URL", key="fda", 
                               value="https://www.fda.gov/drugs/postmarket-drug-safety-information-patients-and-providers/xolair-omalizumab-information")
        if fda_url and is_valid_url(fda_url):
            same_as_urls.append(fda_url)
    
    with reg_cols[1]:
        clinical_trials_url = st.text_input("ClinicalTrials.gov URL", key="clinicaltrials", 
                                         value="https://clinicaltrials.gov/search?term=NCT00377572")
        if clinical_trials_url and is_valid_url(clinical_trials_url):
            same_as_urls.append(clinical_trials_url)
    
    st.markdown("##### Medical Knowledge Graphs")
    kg_cols = st.columns(2)
    with kg_cols[0]:
        wikidata_url = st.text_input("Wikidata URL", key="wikidata", value="https://www.wikidata.org/wiki/Q204711")
        if wikidata_url and is_valid_url(wikidata_url):
            same_as_urls.append(wikidata_url)
    
    with kg_cols[1]:
        wikipedia_url = st.text_input("Wikipedia URL", key="wikipedia", value="https://en.wikipedia.org/wiki/Omalizumab")
        if wikipedia_url and is_valid_url(wikipedia_url):
            same_as_urls.append(wikipedia_url)
    
    st.markdown("##### Standardized Ontologies")
    onto_cols = st.columns(2)
    with onto_cols[0]:
        mesh_url = st.text_input("MeSH URL", key="mesh", value="https://meshb.nlm.nih.gov/record/ui?ui=C079635")
        if mesh_url and is_valid_url(mesh_url):
            same_as_urls.append(mesh_url)
    
    with onto_cols[1]:
        atc_url = st.text_input("WHO ATC URL", key="atc", value="https://www.whocc.no/atc_ddd_index/?code=R03DX05")
        if atc_url and is_valid_url(atc_url):
            same_as_urls.append(atc_url)
    
    st.markdown("##### Additional URLs")
    additional_cols = st.columns(2)
    with additional_cols[0]:
        pubmed_url = st.text_input("PubMed URL (Key Publication)", key="pubmed", 
                                  value="https://pubmed.ncbi.nlm.nih.gov/19818196/")
        if pubmed_url and is_valid_url(pubmed_url):
            same_as_urls.append(pubmed_url)
    
    with additional_cols[1]:
        other_url = st.text_input("Other Authoritative URL", key="other")
        if other_url and is_valid_url(other_url):
            same_as_urls.append(other_url)
    
    if st.button("Find Similar Sites", key="find_similar"):
        if drug_name:
            with st.spinner("Searching for similar authoritative websites..."):
                similar_sites = find_similar_websites(drug_name, generic_name, drug_class)
                
                if similar_sites:
                    st.success(f"Found {len(similar_sites)} similar websites")
                    
                    # Group by category
                    categories = {}
                    for site in similar_sites:
                        category = site["category"]
                        if category not in categories:
                            categories[category] = []
                        categories[category].append(site)
                    
                    # Display by category
                    for category, sites in categories.items():
                        st.markdown(f"#### {category}")
                        for site in sites:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.markdown(f"**{site['name']}** ({site['type']}) - {site['priority']} Priority")
                                st.markdown(f"URL: {site['url']}")
                            with col2:
                                if st.button(f"Add to sameAs", key=f"add_{site['url']}"):
                                    if site['url'] not in same_as_urls:
                                        same_as_urls.append(site['url'])
                                        st.success(f"Added {site['url']} to sameAs list")
                            st.markdown("---")
                else:
                    st.warning("No similar websites found")
        else:
            st.error("Please enter a drug name to find similar websites")
    
    webpage_url = st.text_input("Your Webpage URL (optional)", key="drug_webpage_url", value="https://www.xolair.com")
    
    if st.button("Generate Drug Schema", key="gen_drug_btn"):
        if drug_name and drug_description:
            drug_schema = generate_drug_schema(
                drug_name, 
                generic_name,
                drug_description, 
                manufacturer, 
                active_ingredient, 
                drug_class, 
                prescription_status, 
                same_as_urls,
                medical_codes,
                related_conditions
            )
            
            st.subheader("Generated Schema")
            st.json(drug_schema)
            
            schema_json_str = json.dumps(drug_schema, indent=2)
            st.code(f'<script type="application/ld+json">\n{schema_json_str}\n</script>', language='html')
            
            if webpage_url and is_valid_url(webpage_url):
                with st.spinner("Fetching and updating the webpage..."):
                    html_content = get_webpage_content(webpage_url)
                    if html_content:
                        updated_html = inject_schema_into_html(html_content, drug_schema)
                        st.download_button(
                            label="Download Updated HTML",
                            data=updated_html,
                            file_name=f"{drug_name.lower().replace(' ', '_')}_with_schema.html",
                            mime="text/html"
                        )
        else:
            st.error("Drug Name and Description are required fields")

with tab3:
    st.header("Generate Clinical Trial Schema")
    
    trial_id = st.text_input("Clinical Trial ID", key="trial_id", value="NCT00377572")
    trial_name = st.text_input("Trial Name", key="trial_name", 
                              value="A Study of Xolair (Omalizumab) in Patients With Moderate to Severe Persistent Asthma")
    trial_description = st.text_area("Trial Description", key="trial_desc", 
                                   value="This randomized, double-blind, placebo-controlled study evaluates the efficacy and safety of Xolair in patients with moderate to severe persistent asthma who remain symptomatic despite treatment with inhaled corticosteroids.")
    trial_sponsor = st.text_input("Trial Sponsor", key="trial_sponsor", value="Genentech")
    health_condition = st.text_input("Health Condition", key="health_condition", value="Moderate to Severe Persistent Asthma")
    trial_drug = st.text_input("Drug Being Studied", key="trial_drug", value="Xolair (omalizumab)")
    
    trial_status = st.selectbox(
        "Trial Status",
        ["Recruiting", "Active, not recruiting", "Completed", "Terminated", "Withdrawn", "Not yet recruiting"],
        key="trial_status",
        index=2  # Completed
    )
    
    trial_phase = st.selectbox(
        "Trial Phase",
        ["Phase 1", "Phase 2", "Phase 3", "Phase 4", "Early Phase 1", "Not Applicable"],
        key="trial_phase",
        index=2  # Phase 3
    )
    
    st.subheader("Related Publications")
    st.markdown("Add key publications from this trial (improves scientific credibility)")
    
    pub_cols = st.columns(2)
    related_publications = []
    
    with pub_cols[0]:
        pub_url1 = st.text_input("Publication URL", key="pub_url1", 
                               value="https://pubmed.ncbi.nlm.nih.gov/19818196/")
        pub_title1 = st.text_input("Publication Title", key="pub_title1", 
                                 value="Safety of omalizumab in asthma: a systematic review and meta-analysis of randomized controlled trials")
        if pub_url1 and pub_title1:
            related_publications.append({"url": pub_url1, "title": pub_title1})
    
    with pub_cols[1]:
        pub_url2 = st.text_input("Publication URL (Optional)", key="pub_url2", 
                               value="https://pubmed.ncbi.nlm.nih.gov/21356516/")
        pub_title2 = st.text_input("Publication Title (Optional)", key="pub_title2", 
                                 value="Omalizumab for asthma in adults and children")
        if pub_url2 and pub_title2:
            related_publications.append({"url": pub_url2, "title": pub_title2})
    
    trial_webpage_url = st.text_input("Trial Webpage URL (optional)", key="trial_webpage_url", 
                                    value="https://www.xolair.com/hcp/asthma/clinical-studies.html")
    
    if st.button("Generate Clinical Trial Schema", key="gen_trial_btn"):
        if trial_id and trial_name and trial_description:
            trial_schema = generate_clinical_trial_schema(
                trial_id,
                trial_name,
                trial_description,
                trial_sponsor,
                health_condition,
                trial_drug,
                trial_status,
                trial_phase,
                related_publications
            )
            
            st.subheader("Generated Schema")
            st.json(trial_schema)
            
            schema_json_str = json.dumps(trial_schema, indent=2)
            st.code(f'<script type="application/ld+json">\n{schema_json_str}\n</script>', language='html')
            
            if trial_webpage_url and is_valid_url(trial_webpage_url):
                with st.spinner("Fetching and updating the webpage..."):
                    html_content = get_webpage_content(trial_webpage_url)
                    if html_content:
                        updated_html = inject_schema_into_html(html_content, trial_schema)
                        st.download_button(
                            label="Download Updated HTML",
                            data=updated_html,
                            file_name=f"clinical_trial_{trial_id.lower().replace(' ', '_')}_with_schema.html",
                            mime="text/html"
                        )
        else:
            st.error("Trial ID, Name, and Description are required fields")

with tab4:
    st.header("Find Authoritative Sites")
    
    search_drug_name = st.text_input("Drug Name", key="search_drug_name", value="Xolair")
    search_generic_name = st.text_input("Generic Name", key="search_generic_name", value="omalizumab")
    search_drug_class = st.text_input("Drug Class (Optional)", key="search_drug_class", value="Monoclonal antibody")
    
    if st.button("Search", key="search_btn"):
        if search_drug_name:
            with st.spinner("Searching for authoritative websites..."):
                sites = find_similar_websites(search_drug_name, search_generic_name, search_drug_class)
                
                if sites:
                    st.success(f"Found {len(sites)} relevant websites")
                    
                    # Group by category for display
                    categories = {}
                    for site in sites:
                        category = site["category"]
                        if category not in categories:
                            categories[category] = []
                        categories[category].append(site)
                    
                    # Create tabs for each category
                    category_tabs = st.tabs(list(categories.keys()))
                    
                    for i, (category, tab) in enumerate(zip(categories.keys(), category_tabs)):
                        with tab:
                            # Create a dataframe for this category
                            site_data = {
                                "Name": [site["name"] for site in categories[category]],
                                "Type": [site["type"] for site in categories[category]],
                                "URL": [site["url"] for site in categories[category]],
                                "Priority": [site["priority"] for site in categories[category]]
                            }
                            
                            st.dataframe(site_data)
                    
                    # Create a downloadable list
                    sites_json = json.dumps(sites, indent=2)
                    st.download_button(
                        label="Download Sites as JSON",
                        data=sites_json,
                        file_name=f"{search_drug_name.lower().replace(' ', '_')}_sites.json",
                        mime="application/json"
                    )
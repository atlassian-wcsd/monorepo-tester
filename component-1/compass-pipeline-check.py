import yaml
import requests
import sys
import base64
import json
import os


url = os.getenv("ATLASSIAN_SITE")+ "/gateway/api/graphql"
api_token = os.getenv("ATLASSIAN_API_TOKEN")
email = os.getenv("ATLASSIAN_API_USER")
auth_header = f"{email}:{api_token}"
encoded_auth_header = base64.b64encode(auth_header.encode('utf-8')).decode('utf-8')
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Basic {encoded_auth_header}",
}
scorecardId = os.getenv("ATLASSIAN_SCORECARD_ID")
# "ari:cloud:compass:a1fe6479-0253-4bf2-8cb9-3c7c70456ae4:component/6769ddfe-0469-47f0-8807-9e419c80f596/49d4738d-ecd6-49ef-9fc1-b01e0772c214"

# Adding some documentation

def read_compass_yaml(file_path):
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def construct_graphql_query():
   return """
    query compass_component_getComponentScorecardsWithScores($componentId: ID!) {
  compass @optIn(to: "compass-beta") {
    component(id: $componentId) {
      __typename
      ... on CompassComponent {
        ...CompassComponentCore
        name
        typeId
        scorecards {
          id
          name
          componentTypeIds
          campaigns {
            nodes {
              ...CompassCampaignCore
              __typename
            }
            __typename
          }
          applicationModel {
            ... on CompassScorecardAutomaticApplicationModel {
              applicationType
              componentTypeIds
              __typename
            }
            ... on CompassScorecardManualApplicationModel {
              applicationType
              __typename
            }
            __typename
          }
          scorecardScore(query: {componentId: $componentId}) {
            ...CompassScorecardScoreFragment
            __typename
          }
          criterias {
            ...CompassScorecardCriteriaExploded
            ...CompassScorecardCriteriaScore
            __typename
          }
          isDeactivationEnabled
          __typename
        }
        __typename
      }
      ... on QueryError {
        message
        extensions {
          statusCode
          errorType
          __typename
        }
        __typename
      }
    }
    __typename
  }
}

fragment CompassCampaignCore on CompassCampaign {
  id
  name
  description
  status
  startDate
  dueDate
  __typename
}

fragment CompassComponentCore on CompassComponent {
  id
  __typename
}

fragment CompassScorecardCriteriaExploded on CompassScorecardCriteria {
  __typename
  id
  name
  weight
  description
  ... on CompassHasLinkScorecardCriteria {
    linkType
    textComparator
    textComparatorValue
    __typename
  }
  ... on CompassHasFieldScorecardCriteria {
    fieldDefinition {
      id
      name
      __typename
    }
    __typename
  }
  ... on CompassHasMetricValueScorecardCriteria {
    comparatorValue
    comparator
    metricDefinition {
      id
      type
      name
      format {
        __typename
        ... on CompassMetricDefinitionFormatSuffix {
          suffix
          __typename
        }
      }
      __typename
    }
    __typename
  }
  ... on CompassHasCustomBooleanFieldScorecardCriteria {
    booleanComparator
    booleanComparatorValue
    customFieldDefinition {
      id
      name
      description
      componentTypeIds
      __typename
    }
    __typename
  }
  ... on CompassHasCustomNumberFieldScorecardCriteria {
    numberComparator
    numberComparatorValue
    customFieldDefinition {
      id
      name
      description
      componentTypeIds
      __typename
    }
    __typename
  }
  ... on CompassHasCustomTextFieldScorecardCriteria {
    customFieldDefinition {
      id
      name
      description
      componentTypeIds
      __typename
    }
    __typename
  }
  ... on CompassHasCustomSingleSelectFieldScorecardCriteria {
    membershipComparator
    membershipComparatorValue
    customFieldDefinition {
      id
      name
      description
      componentTypeIds
      options {
        id
        value
        __typename
      }
      __typename
    }
    __typename
  }
  ... on CompassHasCustomMultiSelectFieldScorecardCriteria {
    collectionComparator
    collectionComparatorValue
    customFieldDefinition {
      id
      name
      description
      componentTypeIds
      options {
        id
        value
        __typename
      }
      __typename
    }
    __typename
  }
}

fragment CompassScorecardCriteriaScore on CompassScorecardCriteria {
  scorecardCriteriaScore(query: {componentId: $componentId}) {
    score
    maxScore
    explanation
    dataSourceLastUpdated
    __typename
  }
  __typename
}

fragment CompassScorecardScoreFragment on CompassScorecardScore {
  totalScore
  maxTotalScore
  statusDuration {
    since
    __typename
  }
  status {
    name
    lowerBound
    upperBound
    __typename
  }
  __typename
}    """

def check_scorecard_status(graphql_endpoint, variables):
    query = construct_graphql_query()
    response = requests.post(
        graphql_endpoint,
        data=json.dumps({"query": query, "variables":variables}),
        headers=headers
    )

    if response.status_code != 200:
        raise Exception(f"Query failed with status code {response.status_code}: {response.text}")

    result = response.json()
    
    # Adjust according to the actual structure of your response
    try:
        scorecards = result['data']['compass']['component']['scorecards']
        evaluated_scorecard = next((scorecard for scorecard in scorecards if scorecard['name'] == "Data Encryption Scorecard"), None)
        if evaluated_scorecard:
            status = evaluated_scorecard['scorecardScore']['status']['name']
            print(f"Scorecard Status: {status}")
            if status == "PASSING":
                print("Scorecard meets expectations.")
            else:
                raise Exception("Scorecard does not meet expectations.")
        else:
            raise Exception("Error: Unable to find Scorecard in Scope.")
        
    except KeyError:
        raise Exception("Error: Unexpected response structure.")

def main():
    # Path to the compass.yml file
    yaml_file_path = './compass.yml'

    # Read the YAML file
    compass_data = read_compass_yaml(yaml_file_path)
    # Assuming the component name is stored under a specific key in the YAML file
    # Adjust the key based on your YAML structure
    componentId = compass_data.get('id')  # Change 'component_name' to your actual key
    if not componentId:
        raise Exception("Component id not found in the compass.yml file.")
    # Check the scorecard status
    try:
        variables = {"componentId": componentId }
        check_scorecard_status(url, variables)
        print(f"The Scorecard status for '{componentId}' is passing.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
if __name__ == "__main__":
    main()
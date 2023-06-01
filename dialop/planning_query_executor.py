from copy import deepcopy

import numpy as np
import openai
import pyparsing as pp
from pyparsing import OneOrMore, Suppress, delimited_list, one_of
from pyparsing.exceptions import ParseException

from dialop.templates import QueryExecutorTemplate


def create_search_api():
  LP = Suppress("(")
  RP = Suppress(")")
  LB = Suppress("[")
  RB = Suppress("]")
  Q = Suppress('"') | Suppress("'")


  valid_name_chars = pp.alphanums + "'"
  string = (OneOrMore(pp.Word(valid_name_chars))).set_parse_action(" ".join)
  filt = pp.Group(pp.Word(pp.alphas) + one_of("== >= <=") +
                  pp.Word(pp.alphanums))
  dist_to = pp.Group("distance_to" + LP + string + RP)
  key = one_of("fields filters text_query sort_by") + Suppress("=")
  value = (string |
           LB + pp.Group(delimited_list(dist_to | filt | pp.Word(pp.alphanums))) + RB |
           Q + string + Q
           )
  search = "Search" + LP + delimited_list(pp.dict_of(key, value)) + RP
  return search
search_api = create_search_api()

class SearchError(Exception):
    pass

class StaticQueryExecutor:
    def __init__(self, sites):
        self.sites = sites

    def _parse_query(self, query_str):
        try:
            query = search_api.parse_string(query_str, parse_all=True).as_dict()
        except ParseException:
            import pdb; pdb.set_trace()
            raise SearchError(f"Invalid search syntax: {query_str}.")
        print("..searching with query: ", query)
        return query

    def __call__(self, query_str):
        """Search the database of sites with a query string.

        Parses query string into a `query` Dict, with keys:
        - fields (required): fields to return from each result
        - filters: list of tuples (field, comparator, value) to filter
          sites by
        - text_query: freeform text query (searches over event features)
        - sort_by: list of fields or function call to `distance_to` to sort
          results by (in asc order). Sorting by a field also returns it in
          the results.

        Returns:
            result of the search, as a string
        """
        query = self._parse_query(query_str)
        results = deepcopy(self.sites)
        return_fields = [self._remap(k) for k in query["fields"]]
        for filt in query.get("filters", []):
            field, comparator, value = filt
            field = self._remap(field)
            if field not in ["name", "etype", "est_price"]:
                raise SearchError(f"You cannot filter by {field}."
                                  "Try searching with a text query instead.")
            def filt_fn(x):
                if comparator == "==":
                    return str(x[field]) == str(value)
                if comparator == ">=":
                    return float(x[field]) >= float(value)
                if comparator == "<=":
                    return float(x[field]) <= float(value)
            results = [r for r in results if filt_fn(r)]
        results = [r for r in results if query.get("text_query", "") in str(r)]
        for sort in query.get("sort_by", []):
            if len(sort) == 2:
                func, arg = sort
                assert func == "distance_to", \
                    f"Sorting by unknown function?: {sort}"
                target_evt = [r for r in self.sites if arg in str(r)]
                assert len(target_evt) == 1, \
                    f"More than one event found for search?: {sort}"
                target_evt = target_evt[0]
                for r in results:
                    r["distance"] = self.distance(r, target_evt)
                sort = "distance"
            results = sorted(results, key=lambda r: r[self._remap(sort)])
            return_fields.append(sort)
        results = [{k: v for k, v in r.items() if k in return_fields} \
                   for r in results]
        return self._format_results(results)

    def distance(self, s1, s2) -> float:
        dist = np.linalg.norm(np.array(s1["loc"]) - np.array(s2["loc"]))
        dist *= 69
        dist = round(dist * 10) / 10
        return dist

    def _format_results(self, results) -> str:
        if len(results) == 0:
            return "Search Results: No results\n"
        result_str = f"Search Results ({len(results)}):\n"
#        import pdb; pdb.set_trace()
        keys = ["name"] + [self._unremap(k) for k in results[0].keys() if k != "name"]
        result_str += "|".join(keys)
        keys = [self._remap(k) for k in keys]
        for r in results:
            result_str += f"\n{'|'.join(str(r[k]) for k in keys)}"
        return result_str

    def _remap(self, key):
        api_to_internal_name = {
            "category": "etype",
            "price": "est_price",
        }
        if key in api_to_internal_name:
            return api_to_internal_name[key]
        return key

    def _unremap(self, key):
        internal_name_to_api = {
            "etype": "category",
            "est_price": "price",
        }
        if key in internal_name_to_api:
            return internal_name_to_api[key]
        return key

class GPT3QueryExecutor:
    def __init__(self, sites):
        self.prompt = self._construct_prompt(sites)
        self.model = "text-davinci-003"

    def _construct_prompt(self, sites):
        sites = deepcopy(sites)
        test_searches = [
            "Search(fields=[name], filters=[category == landmark])",
            "Search(fields=[name], filters=[category == concert])",
            "Search(fields=[name], text_query=live music)",
            "Search(fields=[name, price], text_query=live music, filters=[price <= 40])",
            "Search(fields=[name, price], filters=[category == restaurant, price <= 10], sort_by=[distance_to(The Mall)])",
            "Search(fields=[name, price, distance], filters=[category == restaurant], sort_by=[distance_to(The Mall), price])",
            """Search(fields=[name], text_query="good for kids", filters=[category == park], sort_by=[distance_to(Saul's)])""",
            "Search(fields=[name], filters=[vegan == true])",
        ]
        static_search = StaticQueryExecutor(sites)
        def get_result_str(q):
            try:
                return static_search(q)
            except SearchError as e:
                return str(e)
        examples = [{"query": q, "result": get_result_str(q)}
                    for q in test_searches]

        # Remove some fields to save context length
        for s in sites:
            del s["type"]
            del s["id_"]
            s["loc"] = [round(s["loc"][0], 2), round(s["loc"][1], 2)]

        prompt = QueryExecutorTemplate.render(
            sites=sites,
            example_queries=examples
        )
        return prompt

    def __call__(self, query_str):
        prompt = self.prompt + f"Query: {query_str}\nResult:\n"
        response = openai.Completion.create(
            model=self.model,
            prompt=prompt,
            temperature=0.1,
            max_tokens=256,
            top_p=.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=["\n\n", "Query", "Query:"]
        )
        print(response)
        return response["choices"][0]["text"]

    def distance(self, s1, s2) -> float:
        dist = np.linalg.norm(np.array(s1["loc"]) - np.array(s2["loc"]))
        dist *= 69
        dist = round(dist * 10) / 10
        return dist

# -*- coding: utf-8 -*-

import re
from datetime import datetime
import uuid
import time
import logging
from pprint import pprint

from flask import current_app, abort, request

from widukind_api import constants
from widukind_common.flask_utils.queries import *

logger = logging.getLogger(__name__)

def data_aggregate(query, start_period=None, end_period=None, limit=None, db=None):
    
    start = time.time()
    
    project = {
        '_id': 0,
        'key': 1,
        'name': 1,
        'values.period': 1, 
        'values.value': 1,
        'values.ordinal': 1, 
        'dimensions': 1,
        'attributes': 1,
    }
    
    match_values = None
    
    if start_period and end_period:
        match_values = {"values.ordinal": {"$gte": start_period, "$lte": end_period}}
    elif start_period:    
        match_values = {"values.ordinal": {"$gte": start_period}}
    elif end_period:    
        match_values = {"values.ordinal": {"$lte": end_period}}
    
    group = { 
        "_id": {
            "key": "$key",
            "name" : "$name",
            "dimensions" : "$dimensions",
            "attributes" : "$attributes",
        },
        "values": {
            "$push": {
                "value": "$values.value", 
                "period": "$values.period"
            }
        },
    }
    
    pipeline = []
    pipeline.append({"$match": query})
    
    if limit:
        pipeline.append({"$limit": limit })
    
    pipeline.append({'$project': project})
    pipeline.append({"$unwind": "$values"})
    
    if match_values:
        pipeline.append({"$match": match_values})
    
    pipeline.append({"$group": group })
    
    print("----------------------------------")
    pprint(pipeline)
    print("----------------------------------")
    
    result = list(col_series(db).aggregate(pipeline, allowDiskUse=True))

    end = time.time() - start
    msg = "sdmx-data-aggregate - %.3f"
    logger.info(msg % end)
    
    return result

def data_query(dataset_code, provider_name=None, filters=None, 
               start_period=None, end_period=None,
               limit=None, get_ordinal_func=None, db=None):

    query_ds = {'enable': True, 'dataset_code': dataset_code}
    if provider_name:
        query_ds["provider_name"] = provider_name
    projection_ds = {"name": True, "dataset_code": True, "slug": True,
                     "provider_name": True, "dimension_keys": True}
    dataset_doc = col_datasets(db).find_one(query_ds, projection_ds)
    
    if not dataset_doc:
        abort(404)

    if start_period:
        start_period = get_ordinal_func(start_period)
    if end_period:
        end_period = get_ordinal_func(end_period)

    query = {"provider_name": dataset_doc["provider_name"],
             "dataset_code": dataset_doc["dataset_code"]}
    
    if filters and filters != "all": 
        _filters = filters.split(".")
        if not len(_filters) == len(dataset_doc["dimension_keys"]):
            #print("abort filter required !", len(_filters), len(dataset_doc["dimension_keys"]))
            abort(404, "abort filter required !")
        for i, dim in enumerate(dataset_doc["dimension_keys"]):
            if not _filters[i]:
                continue
            query["dimensions."+ dim] = {"$in": _filters[i].split("+")}
    
    """
    TODO: Compter doc total sans filtrage pour déterminer si obligation filtrage
    """

    print("--------------- QUERY ----------------------")
    pprint(query)
    print("--------------------------------------------")
    
    if not start_period and not end_period:
        projection = {
            "_id": False,
            "key": True, "name": True,
            'values.period': True, 'values.value': True, 'values.ordinal': True, 
            'dimensions': True, 'attributes': True,
        }
        cursor = col_series(db).find(query, projection)
        if limit:
            cursor = cursor.limit(limit)
        docs = list(cursor)
    else:
        cursor = data_aggregate(query, 
                                start_period=start_period, 
                                end_period=end_period, 
                                limit=limit,
                                db=db)
        docs = []
        for doc in cursor:
            docs.append({
                "key": doc["_id"]["key"],
                "name": doc["_id"]["name"],
                "dimensions": doc["_id"]["dimensions"],
                "attributes": doc["_id"]["attributes"],
                "values": doc["values"],
            })
    
    #count = len(docs)

    now = str(datetime.utcnow().isoformat())
    
    return {
        "provider_name": dataset_doc["provider_name"],
        "dataset_name": dataset_doc["name"],
        "dataset_code": dataset_doc["dataset_code"],
        "dataset_slug": dataset_doc["slug"],
        "message_id": str(uuid.uuid4()),
        "prepared_date": now,
        "validFromDate": now,
        "objects": docs,
    }


# -*- coding: utf-8 -*-

def eval(source, target):
    source = list(source or "")
    target = list(target or "")
    if not source:
        return len(target)
    if not target:
        return len(source)

    previous = list(range(len(target) + 1))
    for i, source_item in enumerate(source, 1):
        current = [i]
        for j, target_item in enumerate(target, 1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (source_item != target_item)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]

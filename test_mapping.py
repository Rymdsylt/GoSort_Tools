import json

# Simple unit-style test to simulate fetching mapping and rendering menu order

def render_menu_from_mapping(mapping):
    # Default mapping consistent with GoSort.ino
    default_mapping = {'zdeg': 'bio', 'ndeg': 'nbio', 'odeg': 'hazardous', 'mdeg': 'mixed'}
    merged = default_mapping.copy()
    merged.update(mapping or {})

    menu_order = []
    for key in ['zdeg', 'ndeg', 'odeg', 'mdeg']:
        if key in merged:
            menu_order.append((key, merged[key]))

    trash_labels = {
        'bio': 'Biodegradable',
        'nbio': 'Non-Biodegradable',
        'hazardous': 'Hazardous',
        'mixed': 'Mixed Waste'
    }

    out = []
    for idx, (deg, ttype) in enumerate(menu_order, 1):
        label = trash_labels.get(ttype, ttype)
        out.append(f"{idx}. {label} ({deg} -> {ttype})")

    return out


def test_default_mapping():
    out = render_menu_from_mapping(None)
    assert len(out) == 4
    assert 'Biodegradable' in out[0]
    assert 'Non-Biodegradable' in out[1]
    assert 'Hazardous' in out[2]
    assert 'Mixed Waste' in out[3]
    print('test_default_mapping passed')


def test_server_mapping_override():
    server = {'zdeg': 'nbio', 'ndeg': 'bio', 'odeg': 'mixed', 'mdeg': 'hazardous'}
    out = render_menu_from_mapping(server)
    assert 'Non-Biodegradable' in out[0]
    assert 'Biodegradable' in out[1]
    assert 'Mixed Waste' in out[2]
    assert 'Hazardous' in out[3]
    print('test_server_mapping_override passed')


if __name__ == '__main__':
    test_default_mapping()
    test_server_mapping_override()
    print('All mapping/menu tests passed')

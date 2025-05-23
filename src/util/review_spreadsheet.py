import xlsxwriter
from .log_config import setup_logging
import os

logger = setup_logging("review_spreadsheet")

def write_section_comparison(worksheet, start_row, section_data, formats, max_points_per_section):
    logger.info(f"write_section_comparison: section_data={section_data}")
    current_row = start_row
    section_points = 0.0
    
    # Count total elements (edges + attributes)
    edge_count = len(section_data.get('edges', {}).get('elements', {}))
    attr_count = len(section_data.get('attr', {}).get('elements', {}))
    total_elements = edge_count + attr_count
    
    # Assign points per element, capped at max_points_per_section
    points_per_element = max_points_per_section / total_elements if total_elements > 0 else max_points_per_section
    
    # Process edges
    if 'edges' in section_data:
        edges = section_data['edges'].get('elements', {})
        for item, score in edges.items():
            worksheet.write(current_row, 0, f"Edge: {item}", formats['cell'])
            worksheet.write(current_row, 1, "✓", formats['cell_center'])
            worksheet.write(current_row, 2, "✓", formats['cell_center'])
            worksheet.write(current_row, 3, score, formats['percent'])
            worksheet.write(current_row, 4, points_per_element, formats['number'])
            worksheet.write(current_row, 5, score * points_per_element, formats['number'])
            section_points += score * points_per_element
            current_row += 1
        current_row += 1
    
    # Process attributes
    if 'attr' in section_data:
        attrs = section_data['attr'].get('elements', {})
        for item, score in attrs.items():
            worksheet.write(current_row, 0, f"Attr: {item}", formats['cell'])
            worksheet.write(current_row, 1, "✓", formats['cell_center'])
            worksheet.write(current_row, 2, "✓", formats['cell_center'])
            worksheet.write(current_row, 3, score, formats['percent'])
            worksheet.write(current_row, 4, points_per_element, formats['number'])
            worksheet.write(current_row, 5, score * points_per_element, formats['number'])
            section_points += score * points_per_element
            current_row += 1
    
    # Write subtotal
    worksheet.write(current_row, 0, "Zwischensumme", formats['cell_bold'])
    worksheet.write(current_row, 3, section_points / max_points_per_section if max_points_per_section > 0 else 0.0, formats['percent'])
    worksheet.write(current_row, 4, max_points_per_section, formats['number'])
    worksheet.write(current_row, 5, section_points, formats['number'])
    current_row += 1
    
    return current_row, section_points

def create_review_spreadsheet(grading_data: dict, f_path: str, filename: str, exercise_type: str = "ER") -> None:
    f_path = f_path.replace("submission", "graded")
    output_dir = os.path.dirname(f_path)
    filename = filename[:-5]
    os.makedirs(output_dir, exist_ok=True)
    output_filename = f"{output_dir}/{filename}_Bewertung.xlsx"
    workbook = xlsxwriter.Workbook(output_filename)
    worksheet = workbook.add_worksheet("Bewertung")
    # Define formats
    formats = {
        'title': workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'}),
        'header': workbook.add_format({'bold': True, 'bg_color': '#D3D3D3'}),
        'subheader': workbook.add_format({'bold': True, 'bg_color': '#E0E0E0'}),
        'cell': workbook.add_format({'border': 1}),
        'cell_center': workbook.add_format({'border': 1, 'align': 'center'}),
        'cell_bold': workbook.add_format({'border': 1, 'bold': True}),
        'number': workbook.add_format({'border': 1, 'num_format': '0.00'}),
        'number_bold': workbook.add_format({'border': 1, 'bold': True, 'num_format': '0.00'}),
        'percent': workbook.add_format({'border': 1, 'num_format': '0%'})
    }
    # Set column widths
    worksheet.set_column('A:A', 40)
    worksheet.set_column('B:F', 15)

    # Title
    worksheet.merge_range('A1:F1', f'{exercise_type} Übung - Bewertungsdetails', formats['title'])

    # Headers
    headers = ['Komponente', 'In Musterlösung', 'In Abgabe', 'Übereinstimmung', 'Maximalpunkte', 'Erreichte Punkte']
    for col, header in enumerate(headers):
        worksheet.write(2, col, header, formats['header'])

    current_row = 3
    total_points = 0.0
    max_points_per_entity = grading_data['Erreichbare_punktzahl'] / len(grading_data['details']) if grading_data['details'] else 20.0

    # Process each entity
    if 'details' in grading_data:
        for entity_name, entity_data in grading_data['details'].items():
            worksheet.merge_range(
                current_row, 0, current_row, 5,
                f'Entität: {entity_name}',
                formats['header']
            )
            current_row += 1
            if entity_data.get('status') == 'missing':
                worksheet.write(current_row, 0, f"{entity_name} missing in submission", formats['cell'])
                worksheet.write(current_row, 1, "✓", formats['cell_center'])
                worksheet.write(current_row, 2, "✗", formats['cell_center'])
                worksheet.write(current_row, 3, 0.0, formats['percent'])
                worksheet.write(current_row, 4, max_points_per_entity, formats['number'])
                worksheet.write(current_row, 5, 0.0, formats['number'])
                current_row += 2
            else:
                # Handle entities with or without edges/attributes
                if not entity_data.get('details', {}).get('edges', {}).get('elements') and \
                   not entity_data.get('details', {}).get('attr', {}).get('elements'):
                    worksheet.write(current_row, 0, f"{entity_name}: No edges or attributes", formats['cell'])
                    worksheet.write(current_row, 1, "✓", formats['cell_center'])
                    worksheet.write(current_row, 2, "✓", formats['cell_center'])
                    worksheet.write(current_row, 3, 1.0, formats['percent'])
                    worksheet.write(current_row, 4, max_points_per_entity, formats['number'])
                    worksheet.write(current_row, 5, max_points_per_entity, formats['number'])
                    total_points += max_points_per_entity
                    current_row += 2
                else:
                    current_row, section_points = write_section_comparison(
                        worksheet, current_row, entity_data.get('details', {}),
                        formats, max_points_per_section=max_points_per_entity
                    )
                    total_points += section_points
                    current_row += 1

    # Total points
    worksheet.merge_range(
        current_row, 0, current_row, 3,
        'Gesamtpunkte',
        formats['cell_bold']
    )
    worksheet.write(current_row, 4, grading_data['Erreichbare_punktzahl'], formats['number_bold'])
    worksheet.write(current_row, 5, min(total_points, grading_data['Erreichbare_punktzahl']), formats['number_bold'])

    worksheet.freeze_panes(3, 0)
    workbook.close()
    logger.info(f"Spreadsheet generated: {output_filename}")
    
if __name__ == '__main__':
    #Beispiel-Bewertungsdaten
    beispiel_bewertung = {
        'Gesamtpunktzahl': 85.5,
        'Erreichbare_punktzahl': 100.0,
        'details': {
            'Person': {
                'status': 'nested',
                'score': 0.9,
                'details': {
                    'edges': {
                        'status': 'collection',
                        'score': 0.75,
                        'elements': {
                            'Bestellung': 1.0,
                            'Kunde': 0.8
                        }
                    },
                    'attr': {
                        'status': 'collection',
                        'score': 0.85,
                        'elements': {
                            'Name': 1.0,
                            'Alter': 0.7,
                            'Adresse': 0.9
                        }
                    }
                }
            },
            'Bestellung': {
                'status': 'nested',
                'score': 0.8,
                'details': {
                    'edges': {
                        'status': 'collection',
                        'score': 0.75,
                        'elements': {
                            'Produkt': 1.0,
                            'Person': 0.8
                        }
                    },
                    'attr': {
                        'status': 'collection',
                        'score': 0.85,
                        'elements': {
                            'Bestelldatum': 1.0,
                            'Gesamtbetrag': 0.7
                        }
                    }
                }
            }
        }
    }

    test_filepath = "./test_submission.json"
    test_filename = "student_er_diagram.json"
    
    create_review_spreadsheet(
        grading_data=beispiel_bewertung,
        f_path=test_filepath,
        filename=test_filename,
        exercise_type="ER"
    )
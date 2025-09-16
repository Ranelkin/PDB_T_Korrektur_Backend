import xlsxwriter
import os
from .log_config import setup_logging

__author__ = 'Ranel Karimov, ranelkin@icloud.com'

logger = setup_logging("review_spreadsheet")

def write_section_comparison(worksheet, start_row, section_data, formats, max_points_per_section):
    """Write comparison data for a section to the worksheet.

    Args:
        worksheet: xlsxwriter worksheet object to write to.
        start_row (int): Starting row for writing data.
        section_data (dict): Data for the section, including status and elements.
        formats (dict): Dictionary of xlsxwriter format objects for styling.
        max_points_per_section (float): Maximum points available for the section.

    Returns:
        tuple: (current_row, section_points) - Updated row number and total points earned.
    """
    logger.info(f"write_section_comparison: section_data={section_data}")
    current_row = start_row
    section_points = 0.0
    
    # Handle different section types
    if section_data.get('status') == 'collection' and 'elements' in section_data:
        # Direct collection (e.g., functional dependencies)
        elements = section_data.get('elements', {})
        # Count only solution elements (not extra ones) for points calculation
        solution_elements = {k: v for k, v in elements.items() if not k.endswith(' (extra)')}
        total_elements = len(solution_elements)
        points_per_element = max_points_per_section / total_elements if total_elements > 0 else max_points_per_section
        
        for item, score in elements.items():
            # Don't adjust scores for functional dependencies - use exact scores
            is_extra = item.endswith(' (extra)')
            status_format = formats['cell_green'] if score >= 0.8 else formats['cell_yellow'] if score >= 0.5 else formats['cell_red']
            worksheet.write(current_row, 0, f"Dependency: {item}", status_format)
            worksheet.write(current_row, 1, "✓" if not is_extra else "✗", formats['cell_center'])
            worksheet.write(current_row, 2, "✓" if score > 0 or is_extra else "✗", formats['cell_center'])
            worksheet.write(current_row, 3, score, formats['percent'])
            worksheet.write(current_row, 4, points_per_element if not is_extra else 0, formats['number'])
            worksheet.write(current_row, 5, score * points_per_element if not is_extra else 0, formats['number'])
            if not is_extra:
                section_points += score * points_per_element
            current_row += 1
    else:
        # Nested structure (e.g., ER diagrams)
        edge_count = len(section_data.get('edges', {}).get('elements', {}))
        attr_count = len(section_data.get('attr', {}).get('elements', {}))
        total_elements = edge_count + attr_count
        
        points_per_element = max_points_per_section / total_elements if total_elements > 0 else max_points_per_section
        
        if 'edges' in section_data:
            edges = section_data['edges'].get('elements', {})
            for item, score in edges.items():
                adjusted_score = 1.0 if score >= 0.8 else score
                status_format = formats['cell_green'] if adjusted_score >= 0.8 else formats['cell_yellow'] if adjusted_score >= 0.5 else formats['cell_red']
                worksheet.write(current_row, 0, f"Edge: {item}", status_format)
                worksheet.write(current_row, 1, "✓", formats['cell_center'])
                worksheet.write(current_row, 2, "✓", formats['cell_center'])
                worksheet.write(current_row, 3, adjusted_score, formats['percent'])
                worksheet.write(current_row, 4, points_per_element, formats['number'])
                worksheet.write(current_row, 5, adjusted_score * points_per_element, formats['number'])
                section_points += adjusted_score * points_per_element
                current_row += 1
            current_row += 1
        
        if 'attr' in section_data:
            attrs = section_data['attr'].get('elements', {})
            for item, score in attrs.items():
                adjusted_score = 1.0 if score >= 0.8 else score
                status_format = formats['cell_green'] if adjusted_score >= 0.8 else formats['cell_yellow'] if adjusted_score >= 0.5 else formats['cell_red']
                worksheet.write(current_row, 0, f"Attribute: {item}", status_format)
                worksheet.write(current_row, 1, "✓", formats['cell_center'])
                worksheet.write(current_row, 2, "✓", formats['cell_center'])
                worksheet.write(current_row, 3, adjusted_score, formats['percent'])
                worksheet.write(current_row, 4, points_per_element, formats['number'])
                worksheet.write(current_row, 5, adjusted_score * points_per_element, formats['number'])
                section_points += adjusted_score * points_per_element
                current_row += 1
    
    worksheet.write(current_row, 0, "Subtotal", formats['cell_bold'])
    worksheet.write(current_row, 3, section_points / max_points_per_section if max_points_per_section > 0 else 0.0, formats['percent'])
    worksheet.write(current_row, 4, max_points_per_section, formats['number'])
    worksheet.write(current_row, 5, section_points, formats['number'])
    current_row += 1
    
    return current_row, section_points

def create_review_spreadsheet(grading_data: dict, f_path: str, filename: str, exercise_type: str = "ER") -> None:
    """Create an Excel spreadsheet for grading review.

    Args:
        grading_data (dict): Dictionary containing grading data, including scores and details.
        f_path (str): File path for saving the spreadsheet.
        filename (str): Name of the file (not used in current implementation).
        exercise_type (str, optional): Type of exercise ('ER' or 'FUNCTIONAL'). Defaults to 'ER'.
    """
    output_filename = f_path
    
    logger.info(f"Creating review spreadsheet at: {output_filename}")
    
    # Ensure the directory exists
    output_dir = os.path.dirname(output_filename)
    os.makedirs(output_dir, exist_ok=True)
    
    workbook = xlsxwriter.Workbook(output_filename)
    worksheet = workbook.add_worksheet("Assessment")
    
    formats = {
        'title': workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center', 'bg_color': '#4F81BD', 'font_color': 'white'}),
        'header': workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1, 'align': 'center'}),
        'subheader': workbook.add_format({'bold': True, 'bg_color': '#E6E6E6', 'border': 1}),
        'cell': workbook.add_format({'border': 1, 'font_size': 12}),
        'cell_center': workbook.add_format({'border': 1, 'align': 'center', 'font_size': 12}),
        'cell_bold': workbook.add_format({'border': 1, 'bold': True, 'font_size': 12}),
        'cell_green': workbook.add_format({'border': 1, 'bg_color': '#C6EFCE', 'font_size': 12}),
        'cell_yellow': workbook.add_format({'border': 1, 'bg_color': '#FFEB9C', 'font_size': 12}),
        'cell_red': workbook.add_format({'border': 1, 'bg_color': '#FFC7CE', 'font_size': 12}),
        'number': workbook.add_format({'border': 1, 'num_format': '0.00', 'font_size': 12}),
        'number_bold': workbook.add_format({'border': 1, 'bold': True, 'num_format': '0.00', 'font_size': 12}),
        'percent': workbook.add_format({'border': 1, 'num_format': '0.00%', 'font_size': 12})
    }
    
    worksheet.set_column('A:A', 50)
    worksheet.set_column('B:F', 20)
    
    worksheet.merge_range('A1:F1', f'{exercise_type} Exercise - Assessment Details', formats['title'])
    
    headers = ['Component', 'In Reference', 'In Submission', 'Match (%)', 'Max Points', 'Points Earned']
    for col, header in enumerate(headers):
        worksheet.write(2, col, header, formats['header'])
    
    current_row = 3
    total_points = 0.0
    max_points_per_entity = grading_data['Erreichbare_punktzahl'] / len(grading_data['details']) if grading_data['details'] else grading_data['Erreichbare_punktzahl']

    if grading_data.get('details') == {'status': 'identical'}:
        worksheet.merge_range(current_row, 0, current_row, 5, 'Submission identical to solution', formats['cell_green'])
        worksheet.write(current_row, 1, "✓", formats['cell_center'])
        worksheet.write(current_row, 2, "✓", formats['cell_center'])
        worksheet.write(current_row, 3, 1.0, formats['percent'])
        worksheet.write(current_row, 4, grading_data['Erreichbare_punktzahl'], formats['number'])
        worksheet.write(current_row, 5, grading_data['Erreichbare_punktzahl'], formats['number'])
        total_points = grading_data['Erreichbare_punktzahl']
        current_row += 2
    else:
        for entity_name, entity_data in grading_data['details'].items():
            worksheet.merge_range(
                current_row, 0, current_row, 5,
                f'{"Section" if exercise_type == "FUNCTIONAL" else "Entity"}: {entity_name}',
                formats['subheader']
            )
            current_row += 1
            
            if entity_data.get('status') == 'missing':
                worksheet.write(current_row, 0, f"{entity_name} missing in submission", formats['cell_red'])
                worksheet.write(current_row, 1, "✓", formats['cell_center'])
                worksheet.write(current_row, 2, "✗", formats['cell_center'])
                worksheet.write(current_row, 3, 0.0, formats['percent'])
                worksheet.write(current_row, 4, max_points_per_entity, formats['number'])
                worksheet.write(current_row, 5, 0.0, formats['number'])
                current_row += 2
            elif entity_data.get('status') == 'collection' and exercise_type == "FUNCTIONAL":
                # Handle functional dependencies directly
                current_row, section_points = write_section_comparison(
                    worksheet, current_row, entity_data.get('details', {}).get('dependencies', {}),
                    formats, max_points_per_section=max_points_per_entity
                )
                total_points += section_points
                current_row += 1
            else:
                # Handle ER diagram entities
                if not entity_data.get('details', {}).get('edges', {}).get('elements') and \
                   not entity_data.get('details', {}).get('attr', {}).get('elements'):
                    worksheet.write(current_row, 0, f"{entity_name}: No edges or attributes", formats['cell_green'])
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

    worksheet.merge_range(
        current_row, 0, current_row, 3,
        'Total Score',
        formats['cell_bold']
    )
    worksheet.write(current_row, 4, grading_data['Erreichbare_punktzahl'], formats['number_bold'])
    worksheet.write(current_row, 5, grading_data['Gesamtpunktzahl'], formats['number_bold'])

    worksheet.freeze_panes(3, 0)
    workbook.close()
    logger.info(f"Spreadsheet generated: {output_filename}")
    
if __name__ == '__main__':
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
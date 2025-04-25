import xlsxwriter

def write_section_comparison(worksheet, row, section_data, formats, max_points_per_section=10):
    """
    Schreibt einen Vergleich zwischen Musterlösung und Studentenlösung.
    """
    section_points = 0
    starting_row = row
    
    #Spaltenüberschriften 
    headers = [
        'Komponente',
        'In Musterlösung',
        'In Abgabe',
        'Übereinstimmung',
        'Maximalpunkte',
        'Erreichte Punkte'
    ]
    
    for col, header in enumerate(headers):
        worksheet.write(row, col, header, formats['subheader'])
    row += 1
    
    if isinstance(section_data, dict):
        total_elements = 0
        matched_elements = 0
        
        #edges und attr getrennt verarbeiten
        for key in ['edges', 'attr']:
            if key in section_data:
                elements = section_data[key].get('elements', {})
                for elem_name, score in elements.items():
                    total_elements += 1
                    if score > 0:
                        matched_elements += 1
                    
                    #Zeige ob Element vorhanden ist
                    in_solution = "✓"
                    in_submission = "✓" if score > 0 else "✗"
                    match_percent = score if isinstance(score, (int, float)) else 0
                    
                    element_points = max_points_per_section * score / len(elements)
                    section_points += element_points
                    
                    #Zeileneinträge
                    worksheet.write(row, 0, f"{key}: {elem_name}", formats['cell'])
                    worksheet.write(row, 1, in_solution, formats['cell_center'])
                    worksheet.write(row, 2, in_submission, formats['cell_center'])
                    worksheet.write(row, 3, match_percent, formats['percent'])
                    worksheet.write(row, 4, f"{max_points_per_section/len(elements):.2f}", formats['number'])
                    worksheet.write(row, 5, f"{element_points:.2f}", formats['number'])
                    row += 1

    #Gesamtpunkte 
    if total_elements > 0:
        worksheet.write(row, 0, "Zwischensumme", formats['cell_bold'])
        worksheet.write(row, 3, matched_elements/total_elements, formats['percent'])
        worksheet.write(row, 4, max_points_per_section, formats['number_bold'])
        worksheet.write(row, 5, section_points, formats['number_bold'])
        row += 2  #Leerzeile 
    
    return row, section_points

def create_review_spreadsheet(grading_data: dict, f_path: str, filename: str, exercise_type: str = "ER") -> None:
    """
    Erstellt eine formatierte Excel-Tabelle mit detailliertem Vergleich zwischen 
    Musterlösung und Studentenabgabe.
    """
    f_name_parts = filename.split(".")
    output_filename = f"{f_name_parts[0]}_Bewertung.xlsx"
    
    workbook = xlsxwriter.Workbook(output_filename)
    worksheet = workbook.add_worksheet("Bewertung")
    
    #Erweiterte Formate
    formats = {
        'header': workbook.add_format({
            'bold': True,
            'bg_color': '#4F81BD',
            'font_color': 'white',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        }),
        'subheader': workbook.add_format({
            'bold': True,
            'bg_color': '#B8CCE4',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        }),
        'title': workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'center',
            'valign': 'vcenter'
        }),
        'cell': workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter'
        }),
        'cell_center': workbook.add_format({
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        }),
        'cell_bold': workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter',
            'bold': True
        }),
        'percent': workbook.add_format({
            'border': 1,
            'num_format': '0,00%',
            'align': 'right'
        }),
        'number': workbook.add_format({
            'border': 1,
            'num_format': '#.##0,00',
            'align': 'right'
        }),
        'number_bold': workbook.add_format({
            'border': 1,
            'num_format': '#.##0,00',
            'align': 'right',
            'bold': True
        })
    }
    
    #Spaltenbreiten
    worksheet.set_column(0, 0, 30)  #Komponente
    worksheet.set_column(1, 2, 15)  #Musterlösung & Abgabe
    worksheet.set_column(3, 3, 15)  #Übereinstimmung
    worksheet.set_column(4, 5, 15)  #Punkte
    
    #Titel
    worksheet.merge_range('A1:F1', f'{exercise_type} Übung - Bewertungsdetails', formats['title'])
    
    current_row = 3
    total_points = 0
    
    #Verarbeite jede Hauptkomponente
    if 'details' in grading_data:
        for entity_name, entity_data in grading_data['details'].items():
            #Überschrift für die Entität
            worksheet.merge_range(
                current_row, 0, current_row, 5,
                f'Entität: {entity_name}',
                formats['header']
            )
            current_row += 1
            
            #Verarbeite die Entität
            current_row, section_points = write_section_comparison(
                worksheet, current_row, entity_data.get('details', {}),
                formats,
                max_points_per_section=20  #Punkte pro Entität
            )
            total_points += section_points
    
    #Gesamtpunkte
    current_row += 1
    worksheet.merge_range(
        current_row, 0, current_row, 3,
        'Gesamtpunkte',
        formats['cell_bold']
    )
    worksheet.write(current_row, 4, grading_data['Erreichbare_punktzahl'], formats['number_bold'])
    worksheet.write(current_row, 5, total_points, formats['number_bold'])
    
    #Kopfzeilen fixieren
    worksheet.freeze_panes(3, 0)
    workbook.close()

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
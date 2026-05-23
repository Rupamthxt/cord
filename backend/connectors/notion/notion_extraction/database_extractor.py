"""Database extraction and schema normalization."""

from typing import Dict, Any, List, Optional
from datetime import datetime
from backend.connectors.notion.notion_models.schemas import (
    DatabaseSchema, DatabaseProperty, DatabaseRow
)


class DatabaseExtractor:
    """Extracts and normalizes Notion databases."""
    
    @staticmethod
    def extract_database_schema(database_data: Dict[str, Any]) -> DatabaseSchema:
        """
        Extract and normalize database schema.
        
        Args:
            database_data: Raw database from Notion API
        
        Returns:
            Normalized DatabaseSchema
        """
        properties_list = []
        properties_raw = database_data.get('properties', {})
        
        for prop_name, prop_data in properties_raw.items():
            prop_type = prop_data.get('type', 'unknown')
            
            prop = DatabaseProperty(
                id=prop_data.get('id', prop_name),
                name=prop_name,
                type=prop_type,
                metadata=DatabaseExtractor._extract_property_metadata(prop_data, prop_type)
            )
            properties_list.append(prop)
        
        return DatabaseSchema(
            database_id=database_data['id'],
            title=DatabaseExtractor._extract_database_title(database_data),
            properties=properties_list,
            metadata={
                'icon': database_data.get('icon'),
                'cover': database_data.get('cover'),
                'created_time': database_data.get('created_time'),
                'last_edited_time': database_data.get('last_edited_time'),
            }
        )
    
    @staticmethod
    def _extract_database_title(database_data: Dict[str, Any]) -> str:
        """Extract database title from title array."""
        title_array = database_data.get('title', [])
        if isinstance(title_array, list) and title_array:
            return title_array[0].get('plain_text', '')
        return ''
    
    @staticmethod
    def _extract_property_metadata(
        prop_data: Dict[str, Any],
        prop_type: str
    ) -> Dict[str, Any]:
        """Extract metadata specific to property type."""
        metadata = {}
        
        if prop_type in ['select', 'multi_select']:
            options = prop_data.get(prop_type, {}).get('options', [])
            metadata['options'] = [
                {'id': opt.get('id'), 'name': opt.get('name'), 'color': opt.get('color')}
                for opt in options
            ]
        
        elif prop_type == 'relation':
            metadata['database_id'] = prop_data.get('relation', {}).get('database_id')
        
        elif prop_type == 'rollup':
            metadata['relation_property_id'] = prop_data.get('rollup', {}).get('relation_property_id')
            metadata['rollup_property_id'] = prop_data.get('rollup', {}).get('rollup_property_id')
            metadata['function'] = prop_data.get('rollup', {}).get('function')
        
        elif prop_type == 'number':
            metadata['format'] = prop_data.get('number', {}).get('format')
        
        elif prop_type == 'formula':
            metadata['expression'] = prop_data.get('formula', {}).get('expression')
        
        return metadata
    
    @staticmethod
    def extract_property_value(
        property_name: str,
        property_data: Dict[str, Any]
    ) -> Any:
        """
        Extract typed value from database property.
        
        Args:
            property_name: Name of the property
            property_data: Raw property value from Notion
        
        Returns:
            Extracted value
        """
        prop_type = property_data.get('type', 'unknown')
        
        extractors = {
            'title': lambda p: DatabaseExtractor._extract_rich_text(p.get('title', [])),
            'rich_text': lambda p: DatabaseExtractor._extract_rich_text(p.get('rich_text', [])),
            'text': lambda p: DatabaseExtractor._extract_rich_text(p.get('rich_text', [])),
            'number': lambda p: p.get('number'),
            'checkbox': lambda p: p.get('checkbox', False),
            'select': lambda p: p.get('select', {}).get('name') if p.get('select') else None,
            'multi_select': lambda p: [
                opt.get('name') for opt in p.get('multi_select', [])
            ],
            'date': lambda p: p.get('date', {}).get('start') if p.get('date') else None,
            'email': lambda p: p.get('email'),
            'phone_number': lambda p: p.get('phone_number'),
            'url': lambda p: p.get('url'),
            'relation': lambda p: [rel.get('id') for rel in p.get('relation', [])],
            'rollup': lambda p: p.get('rollup', {}).get('number') or p.get('rollup', {}).get('array'),
            'status': lambda p: p.get('status', {}).get('name') if p.get('status') else None,
            'people': lambda p: [person.get('id') for person in p.get('people', [])],
            'files': lambda p: [
                {'name': f.get('name'), 'url': f.get('file', {}).get('url')}
                for f in p.get('files', [])
            ],
            'created_time': lambda p: p.get('created_time'),
            'created_by': lambda p: p.get('created_by', {}).get('id'),
            'last_edited_time': lambda p: p.get('last_edited_time'),
            'last_edited_by': lambda p: p.get('last_edited_by', {}).get('id'),
        }
        
        extractor = extractors.get(prop_type, lambda p: None)
        return extractor(property_data)
    
    @staticmethod
    def _extract_rich_text(rich_text_array: List[Dict[str, Any]]) -> str:
        """Extract plain text from rich text array."""
        return ''.join(rt.get('plain_text', '') for rt in rich_text_array)
    
    @staticmethod
    def extract_database_row(
        row_data: Dict[str, Any],
        database_id: str
    ) -> DatabaseRow:
        """
        Extract and normalize a single database row/page.
        
        Args:
            row_data: Raw page data from Notion API
            database_id: ID of parent database
        
        Returns:
            Normalized DatabaseRow
        """
        properties = {}
        properties_raw = row_data.get('properties', {})
        
        for prop_name, prop_data in properties_raw.items():
            properties[prop_name] = DatabaseExtractor.extract_property_value(
                prop_name, prop_data
            )
        
        return DatabaseRow(
            row_id=row_data['id'],
            database_id=database_id,
            properties=properties,
            created_time=datetime.fromisoformat(
                row_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                row_data['last_edited_time'].replace('Z', '+00:00')
            ),
            url=row_data.get('url'),
            metadata={
                'archived': row_data.get('archived', False),
                'in_trash': row_data.get('in_trash', False),
            }
        )

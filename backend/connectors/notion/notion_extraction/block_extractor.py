"""Block extraction handlers for different Notion block types."""

from typing import Dict, Any, Optional, List
from datetime import datetime
from backend.connectors.notion.notion_models.schemas import (
    Block, BlockType, RichText, RichTextAnnotation
)


class BlockExtractor:
    """Extracts and normalizes Notion blocks."""
    
    @staticmethod
    def extract_rich_text(raw_rich_text: List[Dict[str, Any]]) -> List[RichText]:
        """Extract rich text with annotations."""
        rich_texts = []
        
        for rt in raw_rich_text:
            text = rt.get('plain_text', '')
            href = rt.get('href')
            
            annotations = rt.get('annotations', {})
            annotation = RichTextAnnotation(
                bold=annotations.get('bold', False),
                italic=annotations.get('italic', False),
                strikethrough=annotations.get('strikethrough', False),
                underline=annotations.get('underline', False),
                code=annotations.get('code', False),
                color=annotations.get('color')
            )
            
            rich_texts.append(
                RichText(text=text, href=href, annotations=annotation)
            )
        
        return rich_texts
    
    @staticmethod
    def extract_plain_text(raw_rich_text: List[Dict[str, Any]]) -> str:
        """Extract plain text from rich text array."""
        return ''.join(rt.get('plain_text', '') for rt in raw_rich_text)
    
    @staticmethod
    def extract_paragraph(block_data: Dict[str, Any]) -> Block:
        """Extract paragraph block."""
        content = block_data.get('paragraph', {})
        plain_text = BlockExtractor.extract_plain_text(
            content.get('rich_text', [])
        )
        rich_text = BlockExtractor.extract_rich_text(
            content.get('rich_text', [])
        )
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.PARAGRAPH,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=plain_text,
            rich_text_content=rich_text,
            metadata={'color': content.get('color')}
        )
    
    @staticmethod
    def extract_heading(
        block_data: Dict[str, Any],
        level: int
    ) -> Block:
        """Extract heading block (1, 2, or 3)."""
        heading_key = f'heading_{level}'
        content = block_data.get(heading_key, {})
        plain_text = BlockExtractor.extract_plain_text(
            content.get('rich_text', [])
        )
        rich_text = BlockExtractor.extract_rich_text(
            content.get('rich_text', [])
        )
        
        block_type = {
            1: BlockType.HEADING_1,
            2: BlockType.HEADING_2,
            3: BlockType.HEADING_3
        }[level]
        
        return Block(
            id=block_data['id'],
            block_type=block_type,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=plain_text,
            rich_text_content=rich_text,
            metadata={'color': content.get('color'), 'is_toggleable': content.get('is_toggleable', False)}
        )
    
    @staticmethod
    def extract_bulleted_list(block_data: Dict[str, Any]) -> Block:
        """Extract bulleted list item."""
        content = block_data.get('bulleted_list_item', {})
        plain_text = BlockExtractor.extract_plain_text(
            content.get('rich_text', [])
        )
        rich_text = BlockExtractor.extract_rich_text(
            content.get('rich_text', [])
        )
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.BULLETED_LIST_ITEM,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=plain_text,
            rich_text_content=rich_text,
            metadata={'color': content.get('color')}
        )
    
    @staticmethod
    def extract_numbered_list(block_data: Dict[str, Any]) -> Block:
        """Extract numbered list item."""
        content = block_data.get('numbered_list_item', {})
        plain_text = BlockExtractor.extract_plain_text(
            content.get('rich_text', [])
        )
        rich_text = BlockExtractor.extract_rich_text(
            content.get('rich_text', [])
        )
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.NUMBERED_LIST_ITEM,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=plain_text,
            rich_text_content=rich_text,
            metadata={'color': content.get('color')}
        )
    
    @staticmethod
    def extract_to_do(block_data: Dict[str, Any]) -> Block:
        """Extract to-do list item."""
        content = block_data.get('to_do', {})
        plain_text = BlockExtractor.extract_plain_text(
            content.get('rich_text', [])
        )
        rich_text = BlockExtractor.extract_rich_text(
            content.get('rich_text', [])
        )
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.TO_DO,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=plain_text,
            rich_text_content=rich_text,
            metadata={
                'checked': content.get('checked', False),
                'color': content.get('color')
            }
        )
    
    @staticmethod
    def extract_toggle(block_data: Dict[str, Any]) -> Block:
        """Extract toggle block."""
        content = block_data.get('toggle', {})
        plain_text = BlockExtractor.extract_plain_text(
            content.get('rich_text', [])
        )
        rich_text = BlockExtractor.extract_rich_text(
            content.get('rich_text', [])
        )
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.TOGGLE,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=plain_text,
            rich_text_content=rich_text,
            metadata={'color': content.get('color')}
        )
    
    @staticmethod
    def extract_code(block_data: Dict[str, Any]) -> Block:
        """Extract code block."""
        content = block_data.get('code', {})
        plain_text = BlockExtractor.extract_plain_text(
            content.get('rich_text', [])
        )
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.CODE,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=plain_text,
            metadata={
                'language': content.get('language', 'text'),
                'caption': BlockExtractor.extract_plain_text(
                    content.get('caption', [])
                )
            }
        )
    
    @staticmethod
    def extract_quote(block_data: Dict[str, Any]) -> Block:
        """Extract quote block."""
        content = block_data.get('quote', {})
        plain_text = BlockExtractor.extract_plain_text(
            content.get('rich_text', [])
        )
        rich_text = BlockExtractor.extract_rich_text(
            content.get('rich_text', [])
        )
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.QUOTE,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=plain_text,
            rich_text_content=rich_text,
            metadata={'color': content.get('color')}
        )
    
    @staticmethod
    def extract_callout(block_data: Dict[str, Any]) -> Block:
        """Extract callout block."""
        content = block_data.get('callout', {})
        plain_text = BlockExtractor.extract_plain_text(
            content.get('rich_text', [])
        )
        rich_text = BlockExtractor.extract_rich_text(
            content.get('rich_text', [])
        )
        
        icon = content.get('icon', {})
        icon_str = icon.get('emoji') or icon.get('external', {}).get('url') or icon.get('file', {}).get('url')
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.CALLOUT,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=plain_text,
            rich_text_content=rich_text,
            metadata={
                'color': content.get('color'),
                'icon': icon_str
            }
        )
    
    @staticmethod
    def extract_child_page(block_data: Dict[str, Any]) -> Block:
        """Extract child page reference."""
        content = block_data.get('child_page', {})
        title = content.get('title', '')
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.CHILD_PAGE,
            has_children=True,
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=title,
            metadata={'title': title}
        )
    
    @staticmethod
    def extract_child_database(block_data: Dict[str, Any]) -> Block:
        """Extract child database reference."""
        content = block_data.get('child_database', {})
        title = content.get('title', '')
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.CHILD_DATABASE,
            has_children=False,
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=title,
            metadata={'title': title}
        )
    
    @staticmethod
    def extract_image(block_data: Dict[str, Any]) -> Block:
        """Extract image metadata."""
        content = block_data.get('image', {})
        type_ = content.get('type', 'external')
        url = content.get(type_, {}).get('url')
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.IMAGE,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=BlockExtractor.extract_plain_text(
                content.get('caption', [])
            ),
            metadata={
                'url': url,
                'type': type_,
                'caption': BlockExtractor.extract_plain_text(
                    content.get('caption', [])
                )
            }
        )
    
    @staticmethod
    def extract_file(block_data: Dict[str, Any]) -> Block:
        """Extract file metadata."""
        content = block_data.get('file', {})
        type_ = content.get('type', 'external')
        url = content.get(type_, {}).get('url')
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.FILE,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=BlockExtractor.extract_plain_text(
                content.get('caption', [])
            ),
            metadata={
                'url': url,
                'type': type_,
                'caption': BlockExtractor.extract_plain_text(
                    content.get('caption', [])
                )
            }
        )
    
    @staticmethod
    def extract_divider(block_data: Dict[str, Any]) -> Block:
        """Extract divider block."""
        return Block(
            id=block_data['id'],
            block_type=BlockType.DIVIDER,
            has_children=False,
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content='---'
        )
    
    @staticmethod
    def extract_bookmark(block_data: Dict[str, Any]) -> Block:
        """Extract bookmark block."""
        content = block_data.get('bookmark', {})
        url = content.get('url')
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.BOOKMARK,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            content=url or '',
            metadata={'url': url}
        )
    
    @staticmethod
    def extract_table(block_data: Dict[str, Any]) -> Block:
        """Extract table block (structure only, rows fetched separately)."""
        content = block_data.get('table', {})
        
        return Block(
            id=block_data['id'],
            block_type=BlockType.TABLE,
            has_children=block_data.get('has_children', False),
            created_time=datetime.fromisoformat(
                block_data['created_time'].replace('Z', '+00:00')
            ),
            last_edited_time=datetime.fromisoformat(
                block_data['last_edited_time'].replace('Z', '+00:00')
            ),
            metadata={
                'has_column_header': content.get('has_column_header', False),
                'has_row_header': content.get('has_row_header', False)
            }
        )
    
    @staticmethod
    def extract_block(block_data: Dict[str, Any]) -> Optional[Block]:
        """
        Extract any block type.
        
        Args:
            block_data: Raw block data from Notion API
        
        Returns:
            Extracted and normalized Block or None if type unsupported
        """
        block_type = block_data.get('type')
        
        extractors = {
            'paragraph': BlockExtractor.extract_paragraph,
            'heading_1': lambda bd: BlockExtractor.extract_heading(bd, 1),
            'heading_2': lambda bd: BlockExtractor.extract_heading(bd, 2),
            'heading_3': lambda bd: BlockExtractor.extract_heading(bd, 3),
            'bulleted_list_item': BlockExtractor.extract_bulleted_list,
            'numbered_list_item': BlockExtractor.extract_numbered_list,
            'to_do': BlockExtractor.extract_to_do,
            'toggle': BlockExtractor.extract_toggle,
            'child_page': BlockExtractor.extract_child_page,
            'child_database': BlockExtractor.extract_child_database,
            'quote': BlockExtractor.extract_quote,
            'code': BlockExtractor.extract_code,
            'callout': BlockExtractor.extract_callout,
            'table': BlockExtractor.extract_table,
            'image': BlockExtractor.extract_image,
            'file': BlockExtractor.extract_file,
            'bookmark': BlockExtractor.extract_bookmark,
            'divider': BlockExtractor.extract_divider,
        }
        
        extractor = extractors.get(block_type)
        if extractor:
            return extractor(block_data)
        
        return None
